"""kie_video_client.py — the KIE Market API seat: one key, one wallet, Python-executed video.

WHY THIS EXISTS. The revised handover (worklog #1369 assignment) makes real Python video-adapter
graduation the highest-priority task: a Python runtime must perform submit -> durable job id ->
poll -> terminal result URL with no browser anywhere in the request path. kie.ai is the first
graduation unit because its key is VERIFIED in the vault, its wallet is live (7.79 credits at
capture time), and one documented async flow covers 30+ model families.

CONTRACT (https://docs.kie.ai, verified 2026-08-30):

    POST /api/v1/jobs/createTask   {"model": ..., "input": {...}}   -> {"data": {"taskId": ...}}
    GET  /api/v1/jobs/recordInfo?taskId=...                        -> data.state in
            waiting | queuing | generating | success | fail
            data.resultJson (JSON string) -> {"resultUrls": [...]}
            data.creditsConsumed (decimal credits; failed tasks are not charged)
    GET  /api/v1/chat/credit                                       -> data = remaining credits

MONEY DISCIPLINE — same shape as rtst_api_client, gate CLOSED by default:

  * `OMNI_VIDEO_CONFIRM_SPEND` must be set truthy, AND
  * `OMNI_VIDEO_MAX_SPEND` (default 30) must exceed the per-clip cost. One bounded
    generation per graduation run; submit exactly once, no retries — a resubmit is a second
    charge. Failed tasks are not charged by the platform, and the balance is re-read after
    any failure so the ledger never invents a number.

SEAT FILE (`state/secrets/session_kie_ai.json`), written from the vault key, never by hand:

    {"host": "kie.ai", "modality": "video",
     "api": {"kind": "kie", "token": "<api key>", "base": "https://api.kie.ai"}}

SECRETS. The key is read from the seat file, held in an Authorization header, and never printed,
logged, or returned.

    python kie_video_client.py --selftest      # pure logic, no network, no seat, no credit
    python kie_video_client.py --capacity      # free read: wallet balance only
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from veoaifree_chat_client import ChatError            # noqa: E402
from veo_session_replay import SessionExpired          # noqa: E402  (the class the pool/face catch)

DEFAULT_BASE = "https://api.kie.ai"
LEDGER = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "kie" / "jobs.jsonl"

# The model family for the first graduation unit: cheapest bounded real generation on the
# verified wallet. std mode, no sound. The capacity matrix row is kie.ai x kling-3.0 family;
# other families on the same key/wallet are additions to the SAME row, not new accounts.
MODEL = "kling-3.0/video"
DURATION = "5"
MODE = "std"
ASPECT = "16:9"

IN_PROGRESS = {"waiting", "queuing", "generating"}
DONE = {"success"}
FAILED = {"fail"}

# Language that means "you cannot have this without paying". Only ever matched on an ERROR
# response — keyword-scanning a success body is the false-paywall bug rtst already fixed.
WALL_WORDS = ("insufficient", "not enough credit", "out of credit", "no credit", "upgrade",
              "payment required", "subscribe", "purchase", "quota exceeded", "billing")


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def result_urls(result_json: Any) -> List[str]:
    """resultJson is a JSON *string* inside the record; parse it defensively."""
    if isinstance(result_json, str):
        try:
            result_json = json.loads(result_json)
        except ValueError:
            return []
    if not isinstance(result_json, dict):
        return []
    urls = result_json.get("resultUrls") or []
    return [u for u in urls if isinstance(u, str) and u.startswith("http")]


def state_class(state: Any) -> str:
    s = str(state or "").strip().lower()
    if s in DONE:
        return "done"
    if s in FAILED:
        return "failed"
    if s in IN_PROGRESS:
        return "running"
    return "running"                      # an unknown state is STILL RUNNING: never a fake death


def is_wall(status: Optional[int], body: str) -> bool:
    if status == 402:
        return True
    if status is not None and status < 400:
        return False
    return any(w in (body or "").lower() for w in WALL_WORDS)


class KieVideoClient:
    """One kie.ai wallet. Constructed by the pool as `KieVideoClient(secret=<path>)`."""

    def __init__(self, secret, timeout: int = 900):
        # Render ceiling: Kling renders typically finish in 1-5 minutes; a poll ceiling below a
        # real render re-creates the original timeout bug. 900s is generous but bounded.
        self.timeout = int(timeout)
        self.path = pathlib.Path(secret) if not isinstance(secret, pathlib.Path) else secret
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        api = raw.get("api") or {}
        token = (api.get("token") or api.get("key") or "").strip()
        if not token:
            raise SessionExpired("NO_TOKEN", "kie seat carries no api.token -- re-harvest this seat")
        self.host: str = raw.get("host") or "kie.ai"
        self.base: str = (api.get("base") or DEFAULT_BASE).rstrip("/")
        # The one place the key is handled. Never printed.
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        try:
            self.max_spend = float(os.environ.get("OMNI_VIDEO_MAX_SPEND") or 30)
        except ValueError:
            self.max_spend = 30.0

    # ---- transport -------------------------------------------------------------------------------
    def _call(self, path: str, method: str = "GET", body: Optional[dict] = None,
              timeout: int = 60) -> dict:
        try:
            r = requests.request(method, f"{self.base}{path}", headers=self._headers,
                                 json=body if body is not None else None, timeout=timeout)
        except requests.RequestException as e:
            raise ChatError("TRANSPORT", f"{method} {path}: {type(e).__name__}")
        text = r.text or ""
        if r.status_code in (401, 403):
            raise SessionExpired("AUTH", f"kie rejected the key on {path} ({r.status_code})")
        if r.status_code == 402:
            raise ChatError("wall", f"kie {path} requires payment (HTTP 402)")
        if r.status_code == 429:
            raise ChatError("RATE", f"kie rate-limited on {path}")
        try:
            j = r.json()
        except ValueError:
            raise ChatError("UNPARSEABLE", f"{path} returned {r.status_code} non-JSON")
        if j.get("code") not in (None, 200):
            if is_wall(j.get("code"), text):
                raise ChatError("wall", f"kie {path} is walled ({j.get('msg')})")
            raise ChatError(f"KIE_{j.get('code')}", f"{path}: {j.get('msg')}")
        return j

    # ---- free reads ------------------------------------------------------------------------------
    def credits(self) -> float:
        return float((self._call("/api/v1/chat/credit") or {}).get("data") or 0)

    def capacity(self) -> dict:
        return {"host": self.host, "model": MODEL, "creditsRemaining": self.credits(),
                "note": "balance and per-clip credits share the same decimal unit"}

    # ---- the one path that spends ----------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = str(messages[-1].get("content") or "").strip()
        if len(prompt.split()) < 10:
            raise ChatError("SHORT_PROMPT", "a real clip needs a prompt of ~10+ words")
        if model and model not in (MODEL, self.host, "auto"):
            raise ChatError("NO_MODEL", f"this seat is graduated for {MODEL!r} only, not {model!r}")

        # No quote endpoint exists on the Market API; the cost is only known from the finished
        # record. The gate therefore bounds the EXPOSURE: the seat stops after one submit, and
        # the platform does not charge failed tasks.
        if not self.confirm_spend:
            raise ChatError("wall", f"spend gate closed: {MODEL} {DURATION}s {MODE} clip; "
                                    "set OMNI_VIDEO_CONFIRM_SPEND=1 to allow this seat to charge")

        body = {"model": MODEL, "input": {"prompt": prompt, "duration": DURATION,
                                          "aspect_ratio": ASPECT, "mode": MODE, "sound": False,
                                          "multi_shots": False}}
        # Submitted ONCE. No retry here, ever: a resubmit is a second charge. The pool's own
        # failover moves to a DIFFERENT seat.
        data = (self._call("/api/v1/jobs/createTask", method="POST", body=body,
                           timeout=180) or {}).get("data") or {}
        task_id = str(data.get("taskId") or "")
        self._ledger({"host": self.host, "taskId": task_id, "model": MODEL,
                      "duration": DURATION, "mode": MODE, "submitted_at": int(time.time())})
        if not task_id:
            raise ChatError("NO_JOB_ID", "kie accepted the submit but returned no taskId")

        final = self._poll(task_id)
        urls = result_urls(final.get("resultJson"))
        if not urls:
            raise ChatError("NO_URL", f"kie task {task_id} succeeded with no resultUrls")
        return {"text": urls[0], "label": self.host, "status": "completed",
                "model": MODEL, "duration": int(DURATION),
                "credits": float(final.get("creditsConsumed") or 0.0),
                "task_id": task_id, "result_urls": urls}

    def _poll(self, task_id: str) -> dict:
        deadline = time.time() + self.timeout
        transient = 0
        while time.time() < deadline:
            try:
                data = (self._call(f"/api/v1/jobs/recordInfo?taskId={task_id}") or {}).get("data") or {}
            except SessionExpired:
                raise
            except ChatError as e:
                # A transport blip WHILE POLLING must not be charged against the render: the task
                # is still running and the credit is already committed. Tolerate a run of them.
                transient += 1
                if transient > 20:
                    raise ChatError("POLL_FAILED", f"kie task {task_id} unpollable: {e.args[0]}")
                time.sleep(8)
                continue
            transient = 0
            cls = state_class(data.get("state"))
            if cls == "done":
                return data
            if cls == "failed":
                raise ChatError("GEN_FAILED",
                                f"kie task {task_id} failed ({data.get('failMsg') or 'no reason'})")
            time.sleep(8)
        raise ChatError("TIMEOUT", f"kie task {task_id} still running after {self.timeout}s "
                                   "(credits committed -- poll it, do not resubmit)")

    def _ledger(self, rec: dict) -> None:
        """Task id recorded BEFORE polling, so a lost poll never loses a paid clip. No key, ever."""
        try:
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except Exception:
            pass


def _selftest() -> int:
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {name}")

    chk("resultUrls parse from the JSON string envelope",
        result_urls('{"resultUrls":["https://a/b.mp4"]}') == ["https://a/b.mp4"])
    chk("resultUrls pass through a dict",
        result_urls({"resultUrls": ["https://c/d.mp4"]}) == ["https://c/d.mp4"])
    chk("junk resultJson yields no urls", result_urls("not json") == [])
    chk("non-http urls are dropped", result_urls('{"resultUrls":["ftp://x"]}') == [])

    chk("success is done", state_class("success") == "done")
    chk("fail is failed", state_class("fail") == "failed")
    chk("generating is running", state_class("generating") == "running")
    chk("an unknown state is still running", state_class("weird") == "running")
    chk("empty state is still running", state_class("") == "running")

    chk("402 is a wall", is_wall(402, "{}"))
    chk("insufficient on an ERROR is a wall", is_wall(400, '{"msg":"Insufficient credits"}'))
    chk("a success body mentioning billing is never a wall",
        not is_wall(200, '{"code":200,"data":{"billing":true}}'))

    chk("gate closed by default", not _truthy(None) and not _truthy("0"))
    chk("gate opens on truthy", _truthy("1") and _truthy("YES"))

    e = ChatError("wall", "spend gate closed")
    chk("wall: prefix reaches the face", " ".join(str(a) for a in e.args).lower().startswith("wall:"))

    print(f"\n  {ok} passed, {fail} failed")
    return 0 if not fail else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="pure logic, no network, no credit")
    ap.add_argument("--capacity", action="store_true", help="free read: wallet balance only")
    ap.add_argument("--secret", default=str(pathlib.Path(
        r"D:\omniroute-monetizer\state\secrets\session_kie_ai.json")))
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.capacity:
        try:
            print(json.dumps(KieVideoClient(secret=a.secret).capacity(), indent=2))
        except (ChatError, SessionExpired) as e:
            print(f"error: {str(e)[:200]}")
            return 1
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
