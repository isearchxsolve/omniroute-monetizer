"""rtst_api_client.py — the API-CREDENTIAL seat: bearer token + documented contract, no replay.

WHY THIS EXISTS. Every other seat in the pool is a REPLAY seat: `capture_sessions_cdp.py` or
`record_video_job.py` recorded a genuine browser exchange, and `universal_replay` swaps the sentinel for
the real prompt (Law 4 -- never reconstruct). rtst.ai is the one provider where that is the wrong shape:
its auth is a plain bearer JWT from `localStorage.auth_token`, not a signed cookie. No DBSC, no device
binding. So the token travels, and the documented REST contract can be called directly from Python with
no browser anywhere in the request path -- which also means there is no recorded exchange to replay and
there never will be.

`session_pool._client_for` therefore dispatches on the seat's declared `api.kind`, not on the host
string, and `PooledSession.dispatchable` accepts `has_api` as well as `has_recording`. Judging an API
seat by `has_recording` alone made it permanently non-dispatchable: `:8189` answered `503 no_capacity`
while the seat held real credits.

SEAT FILE (`state/secrets/session_rtst_ai.json`), written by the harvester, never by hand:

    {"host": "rtst.ai", "modality": "video",
     "api": {"kind": "rtst", "token": "<bearer>", "base": "https://api.rtst.ai"}}

MONEY DISCIPLINE — this is the only client in the pool that can spend a real credit, so the gate is
strict and it is CLOSED by default:

  * `OMNI_VIDEO_CONFIRM_SPEND` must be set truthy, AND
  * a FREE quote must report `can_afford` with `credits_required <= OMNI_VIDEO_MAX_SPEND` (default 30).

A closed gate raises `ChatError("wall", ...)`, so `:8189` reports `wall:` and oioi parks this seat
instead of retrying it 360 times. That is the honest classification: a policy gate does not clear on
retry, exactly like a paywall.

`POST /video/create` is NOT idempotent and the API publishes no idempotency key, so a retry is a second
charge. This client submits **exactly once per call and never retries a submit**; the job id is appended
to the ledger BEFORE polling starts, so a dropped poll loses the poll and not the paid clip.

SECRETS. The token is read from the seat file, held in a header, and never printed, logged, or returned.

    python rtst_api_client.py --selftest        # pure logic, no network, no seat, no credit
    python rtst_api_client.py --capacity        # free reads only: balance + clips affordable
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

DEFAULT_BASE = "https://api.rtst.ai"
LEDGER = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "rtst" / "jobs.jsonl"

# Terminal states seen from GET /video/{id}. Anything unrecognised is treated as STILL RUNNING -- a
# clip wrongly called failed is a wasted credit, and a slow render must never read as a dead one.
DONE = {"completed", "complete", "success", "succeeded", "finished", "done"}
FAILED = {"failed", "error", "cancelled", "canceled", "rejected"}

# Language that means "you cannot have this without paying". Never solved, never worked around (Law 5).
WALL_WORDS = ("insufficient", "not enough credit", "out of credit", "no credit", "upgrade",
              "payment required", "subscribe", "purchase", "quota exceeded", "billing")

URL_FIELDS = ("video_url", "url", "output_url", "download_url", "result_url", "video", "output")


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def pick_url(d: Any) -> Optional[str]:
    """The result URL's field name is not documented; take the first plausible one, one level deep."""
    if not isinstance(d, dict):
        return None
    for k in URL_FIELDS:
        v = d.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    for v in d.values():
        got = pick_url(v)
        if got:
            return got
    return None


def nearest_duration(want: int, allowed: List[int]) -> int:
    """Providers offer DISCRETE durations (3/5/6/8/10s), so `durationSeconds` is a request, not a
    promise. Prefer the longest allowed value that does not exceed the ask -- overshooting pads the
    film with dead frames and costs more credits than it buys. Fall back to the shortest available."""
    opts = sorted({int(a) for a in allowed if str(a).strip().lstrip("-").isdigit()})
    if not opts:
        return int(want)
    under = [o for o in opts if o <= int(want)]
    return under[-1] if under else opts[0]


def is_wall(status: Optional[int], body: str) -> bool:
    """A wall is only ever declared on an ERROR response.

    An earlier version scanned every body for WALL_WORDS and so classified a perfectly good
    `GET /user/credits` 200 as a paywall, because a success payload legitimately mentions billing or
    upgrade fields. Keyword-matching a success body is the same defect as scoring a route "alive"
    because its HTML happened to contain the expected word: the word is not the meaning.
    """
    if status == 402:
        return True                       # unambiguous: Payment Required
    if status is not None and status < 400:
        return False                      # a success is never a wall, whatever words it contains
    return any(w in (body or "").lower() for w in WALL_WORDS)


class RtstApiClient:
    """One rtst.ai seat. Constructed by the pool as `RtstApiClient(secret=<path>)`."""

    def __init__(self, secret, timeout: int = 1800):
        # 1800s, matching VideoUniversalSessionClient. The synchronous pipeline already produced real
        # video and failed ONLY on a timeout; async moved that failure one layer down, so any poll
        # ceiling below a real render re-creates the original bug. A clip legitimately takes minutes.
        self.timeout = int(timeout)
        self.path = pathlib.Path(secret) if not isinstance(secret, pathlib.Path) else secret
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        api = raw.get("api") or {}
        token = (api.get("token") or "").strip()
        if not token:
            raise SessionExpired("NO_TOKEN", "rtst seat carries no api.token -- re-harvest this seat")
        self.host: str = raw.get("host") or "rtst.ai"
        self.base: str = (api.get("base") or DEFAULT_BASE).rstrip("/")
        # The one place the token is handled, so there is exactly one thing to audit. Never printed.
        self._headers = {"Accept": "application/json",
                         "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}"}
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        try:
            self.max_spend = float(os.environ.get("OMNI_VIDEO_MAX_SPEND") or 30)
        except ValueError:
            self.max_spend = 30.0
        self._models: Optional[List[dict]] = None

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
            raise SessionExpired("AUTH", f"rtst rejected the bearer token on {path} ({r.status_code})")
        if r.status_code == 402:
            raise ChatError("wall", f"rtst {path} requires payment (HTTP 402)")
        if r.status_code == 429:
            raise ChatError("RATE", f"rtst rate-limited on {path}")
        try:
            j = r.json()
        except ValueError:
            raise ChatError("UNPARSEABLE", f"{path} returned {r.status_code} non-JSON")
        refused = r.status_code >= 400 or not j.get("success", True)
        if refused:
            # Only NOW is wall language meaningful: the call already failed, so the words explain why.
            if is_wall(r.status_code if r.status_code >= 400 else 400, text):
                raise ChatError("wall", f"rtst {path} is walled (HTTP {r.status_code})")
            raise ChatError(f"HTTP_{r.status_code}", f"{path} refused")
        return j

    # ---- free reads ------------------------------------------------------------------------------
    def credits(self) -> float:
        return float((self._call("/user/credits") or {}).get("credits") or 0)

    def models(self) -> List[dict]:
        if self._models is None:
            self._models = (self._call("/videomodel") or {}).get("data") or []
        return self._models

    def quote(self, *, model: str, duration: int, resolution: int, aspect: str = "16:9",
              audio: bool = False) -> dict:
        # The "p" suffix is required -- the site's own client appends it and the API rejects a bare
        # number. Every cost question is settled here, for free, before anything can be charged.
        q = (f"/video/estimate-credits?model={model}&duration={duration}&resolution={resolution}p"
             f"&audio={'true' if audio else 'false'}&aspect_ratio={aspect}")
        return (self._call(q) or {}).get("data") or {}

    def capacity(self) -> dict:
        """Free: balance plus how many clips it actually buys at the cheapest option on the menu.
        This is what `/v1/video/capacity` should report instead of a hardcoded floor of 1."""
        bal = self.credits()
        best: Optional[tuple] = None
        for m in self.models():
            durs = [int(d) for d in (m.get("duration") or []) if str(d).isdigit()]
            quals = [int(str(q)) for q in (m.get("video_quality") or []) if str(q).isdigit()]
            if not durs or not quals:
                continue
            try:
                q = self.quote(model=m["name"], duration=min(durs), resolution=min(quals))
            except (ChatError, SessionExpired):
                continue                                   # one bad model never hides the rest
            need = float(q.get("credits_required") or 0)
            if need > 0 and (best is None or need < best[1]):
                best = (m["name"], need, min(durs), min(quals))
        unit = best[1] if best else 0.0
        return {"host": self.host, "creditsRemaining": bal,
                "clipsRemaining": int(bal // unit) if unit else 0,
                "cheapest": {"model": best[0], "credits": unit, "duration": best[2],
                             "resolution": best[3]} if best else None}

    def _plan(self, duration: int, model: Optional[str]) -> tuple:
        """Choose (model, duration, resolution, credits) using FREE quotes only. Cheapest wins:
        on a free tier the cheapest clip is the one that buys the most film."""
        menu = [m for m in self.models() if not model or m.get("name") == model]
        if not menu:
            raise ChatError("NO_MODEL", f"rtst has no video model named {model!r}")
        best: Optional[tuple] = None
        for m in menu:
            durs = [int(d) for d in (m.get("duration") or []) if str(d).isdigit()]
            quals = [int(str(q)) for q in (m.get("video_quality") or []) if str(q).isdigit()]
            if not durs or not quals:
                continue
            dur = nearest_duration(duration, durs)
            try:
                q = self.quote(model=m["name"], duration=dur, resolution=min(quals))
            except (ChatError, SessionExpired):
                continue
            # `allowed_durations` from the quote overrides the model metadata when they disagree.
            allowed = q.get("allowed_durations") or []
            if allowed:
                dur = nearest_duration(duration, allowed)
            need = float(q.get("credits_required") or 0)
            if not q.get("can_afford", True):
                continue
            if need > 0 and (best is None or need < best[3]):
                best = (m["name"], dur, min(quals), need)
        if best is None:
            raise ChatError("wall", "no rtst model is affordable at this balance")
        return best

    # ---- the one path that spends ----------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        """Pool-facing entry point, signature-identical to VideoUniversalSessionClient.chat.
        Returns {"text": <url>, "label": host, "status": "completed"}."""
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = messages[-1].get("content") or ""
        if len(prompt.split()) < 10:
            # Measured: the API enforces a minimum prompt length BEFORE the balance check, so a short
            # prompt fails after the gate has already been opened. Catch it here for free.
            raise ChatError("SHORT_PROMPT", "rtst requires a prompt of ~10+ words")
        aspect = kw.get("aspect_ratio") or "16:9"
        want_dur = int(kw.get("duration") or 5)
        image_refs = kw.get("image_refs") or []

        name, dur, res, need = self._plan(want_dur, model)

        if not self.confirm_spend:
            raise ChatError("wall", f"spend gate closed: {name} {dur}s@{res}p costs {need:g} credits; "
                                    f"set OMNI_VIDEO_CONFIRM_SPEND=1 to allow this seat to charge")
        if need > self.max_spend:
            raise ChatError("wall", f"quote {need:g} exceeds OMNI_VIDEO_MAX_SPEND={self.max_spend:g}")

        body = {"prompt": prompt, "model": name, "duration": dur, "resolution": f"{res}p",
                "aspect_ratio": aspect, "audio": False}
        # Submitted ONCE. No retry here, ever: a retry is a second charge and that call is the
        # operator's, not this client's. The pool's own fallback moves to a DIFFERENT seat.
        data = (self._call("/video/create", method="POST", body=body, timeout=180) or {}).get("data") or {}
        vid = str(data.get("id") or data.get("video_id") or data.get("uuid") or "")
        self._ledger({"host": self.host, "id": vid, "model": name, "duration": dur,
                      "resolution": res, "quoted": need, "submitted_at": int(time.time())})
        if not vid:
            url = pick_url(data)                          # some models answer synchronously
            if url:
                return self._result(url, name, dur, image_refs, credits=need)
            raise ChatError("NO_JOB_ID", "rtst accepted the submit but returned no job id")

        final = self._poll(vid)
        url = pick_url(final)
        if not url:
            raise ChatError("NO_URL", f"rtst job {vid} finished with no downloadable url")
        return self._result(url, name, dur, image_refs, credits=need)

    def _result(self, url: str, model: str, duration: int, image_refs: list,
                credits: float = 0.0) -> Dict[str, Any]:
        return {"text": url, "label": self.host, "status": "completed",
                "model": model, "duration": duration,
                # What the clip actually COST, so the :8189 face can report a true creditsSpent
                # instead of 0.0. This is the quoted figure, and rtst has been measured to charge
                # exactly the quote (30->24 on a quote of 6, then 17->11 on the same). Reporting 0.0
                # for a clip that consumed a third of the balance is the same class of lie as a
                # hardcoded clipsRemaining: a number the caller trusts, invented by the callee.
                "credits": float(credits or 0.0),
                # rtst's documented /video/create body has NO image slot. Saying so is the point: a
                # silently dropped imageRef looks like success and yields a character-inconsistent
                # clip. The slot name needs one capture to confirm before this can be honoured.
                "image_refs_applied": False if image_refs else None}

    def _poll(self, vid: str) -> dict:
        deadline = time.time() + self.timeout
        transient = 0
        while time.time() < deadline:
            try:
                d = (self._call(f"/video/{vid}") or {}).get("data") or {}
            except SessionExpired:
                raise
            except ChatError as e:
                # A transport blip WHILE POLLING must not be charged against the render: the clip is
                # still running and the credit is already spent. Tolerate a run of them.
                transient += 1
                if transient > 20:
                    raise ChatError("POLL_FAILED", f"rtst job {vid} unpollable: {e.args[0]}")
                time.sleep(6)
                continue
            transient = 0
            st = str(d.get("status") or d.get("state") or "").lower()
            if st in DONE or pick_url(d):
                return d
            if st in FAILED:
                raise ChatError("GEN_FAILED", f"rtst job {vid} failed ({st or 'no status'})")
            time.sleep(6)
        raise ChatError("TIMEOUT", f"rtst job {vid} still running after {self.timeout}s "
                                  f"(credits already spent -- poll it, do not resubmit)")

    def _ledger(self, rec: dict) -> None:
        """Job id recorded BEFORE polling, so a lost poll never loses a paid clip. No token, ever."""
        try:
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except Exception:
            pass                                          # a ledger failure must not kill a clip


def _selftest() -> int:
    """Pure logic only: no seat file, no network, no credit."""
    ok = fail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {name}")

    chk("nearest picks the longest under the ask", nearest_duration(5, [3, 5, 8]) == 5)
    chk("nearest never overshoots", nearest_duration(5, [3, 8, 10]) == 3)
    chk("nearest falls back up when nothing fits", nearest_duration(2, [5, 8]) == 5)
    chk("nearest survives an empty menu", nearest_duration(7, []) == 7)
    chk("nearest ignores junk entries", nearest_duration(6, ["5", "x", 8]) == 5)

    chk("402 is a wall", is_wall(402, "{}"))
    chk("insufficient on an ERROR is a wall", is_wall(400, '{"message":"Insufficient credits"}'))
    chk("upgrade on an ERROR is a wall", is_wall(403, "please upgrade your plan"))
    # The regression that shipped and was caught by --capacity: a SUCCESS body legitimately mentions
    # billing/upgrade/purchase fields, and scanning it for wall words called a good balance a paywall.
    chk("a 200 is never a wall, whatever words it holds",
        not is_wall(200, '{"success":true,"credits":17,"billing":{"can_upgrade":true}}'))
    chk("a clean body is not a wall", not is_wall(200, '{"success":true,"credits":120}'))

    chk("url from the top level", pick_url({"video_url": "https://a/b.mp4"}) == "https://a/b.mp4")
    chk("url one level down", pick_url({"output": {"url": "https://c/d.mp4"}}) == "https://c/d.mp4")
    chk("no url means None", pick_url({"status": "running"}) is None)
    chk("non-dict means None", pick_url("https://nope") is None)

    chk("spend gate closed by default", not _truthy(None) and not _truthy("0") and not _truthy(""))
    chk("spend gate opens on truthy", _truthy("1") and _truthy("true") and _truthy("YES"))

    # The contract that matters most: a wall-kind ChatError must render so :8189's never-retry branch
    # fires. video_jobs_face joins e.args and tests `.startswith("wall:")`.
    e = ChatError("wall", "spend gate closed")
    chk("wall: prefix reaches the face", " ".join(str(a) for a in e.args).lower().startswith("wall:"))
    t = ChatError("TIMEOUT", "still running")
    chk("timeout is NOT a wall",
        not " ".join(str(a) for a in t.args).lower().startswith("wall:"))

    print(f"\n  {ok} passed, {fail} failed")
    return 0 if not fail else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="pure logic, no network, no credit")
    ap.add_argument("--capacity", action="store_true", help="free reads: balance + clips affordable")
    ap.add_argument("--secret", default=str(pathlib.Path(
        r"D:\omniroute-monetizer\state\secrets\session_rtst_ai.json")))
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.capacity:
        try:
            print(json.dumps(RtstApiClient(secret=a.secret).capacity(), indent=2))
        except (ChatError, SessionExpired) as e:
            print(f"error: {str(e)[:200]}")
            return 1
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
