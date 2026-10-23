"""llm7_video_client.py — LLM7 kling video seat: POST /v1/videos async job flow.

WHY THIS EXISTS. Upstream-verified 2026-09-06 (worklog #1675): llm7's /v1/models lists
kling-v3.0-pro ($0.15/s) and kling-v3.0-turbo ($0.095/s) with model_type='video',
capabilities.video_generation=true, video_async=true, supported_seconds 3-15,
720P/1080P. POST /v1/videos exists (401 pattern vs 404 on /v1/video/generations).
The stored connection key is DEAD (invalid_api_key) so the mapping below is UNVERIFIED
until a fresh key from dash.llm7.io arrives (operator action). Wall named, not typed
through (Law 5).

CONTRACT (named transport, UNVERIFIED mapping until a key proves it):

    POST /v1/videos   {"model": "kling-v3.0-turbo", "prompt": "...",
                       optional: "seconds" (3-15), "size" ("720P"|"1080P"),
                       "image" (i2v reference, jpeg/png <=10MB, >=300px)}
                       -> job envelope {"id"|"task_id"|"job_id", "status"}
    GET  /v1/videos/{id} -> {"status": ..., "url"|"video_url"|"data"[]."url"}

modeled on the OpenAI-video family the catalog's schema_endpoints=['openai'] implies;
extraction tolerates the common shapes, the request shape is not guessed twice.

MONEY DISCIPLINE — identical to kie_video_client (gate CLOSED by default):
  * `OMNI_VIDEO_CONFIRM_SPEND` truthy AND `OMNI_VIDEO_MAX_SPEND` (default 30) must
    exceed the estimated per-clip cost. One bounded generation per graduation run;
    submit exactly once, no retries. These models are tier='pro',
    usage_based_only=true — every accepted submit bills per second.

SEAT FILE (`state/secrets/session_llm7_video.json`), written from a fresh vault key:

    {"host": "api.llm7.io", "modality": "video",
     "api": {"kind": "llm7_video", "token": "<api key>",
             "base": "https://api.llm7.io"}}

SECRETS. The key lives only in the seat file and Authorization header; never printed,
logged, or returned.

    python llm7_video_client.py --selftest      # pure logic, no network
    python llm7_video_client.py --capacity      # GET /v1/models video-type check only
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
from veo_session_replay import SessionExpired          # noqa: E402

DEFAULT_BASE = "https://api.llm7.io"
LEDGER = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "llm7" / "jobs.jsonl"

DEFAULT_MODEL = "kling-v3.0-turbo"         # cheapest verified video row ($0.095/s)
DEFAULT_SECONDS = 5                        # supported 3-15; 5s keeps the bounded cost low
TERMINAL_POLL = 1800
POLL_EVERY = 10.0

DONE = {"completed", "succeeded", "success"}
FAILED = {"failed", "error", "cancelled"}

WALL_WORDS = ("insufficient", "not enough credit", "out of credit", "no credit",
              "upgrade", "payment required", "subscribe", "quota exceeded", "billing")


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def extract_video_url(body: Any) -> str:
    """Tolerant extraction from the job-envelope response family. Pure logic, testable."""
    if not isinstance(body, dict):
        return ""
    for key in ("video_url", "url"):
        v = body.get(key)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    data = body.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key in ("video_url", "url"):
                    v = item.get(key)
                    if isinstance(v, str) and v.startswith(("http://", "https://")):
                        return v
    if isinstance(data, dict):
        for key in ("video_url", "url"):
            v = data.get(key)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
    out = body.get("output")
    if isinstance(out, dict):
        return extract_video_url(out)
    res = body.get("result")
    if isinstance(res, dict):
        urls = res.get("resultUrls") or []
        for u in urls if isinstance(urls, list) else []:
            if isinstance(u, str) and u.startswith(("http://", "https://")):
                return u
    return ""


def status_class(state: Any) -> str:
    s = str(state or "").strip().lower()
    if s in DONE:
        return "done"
    if s in FAILED:
        return "failed"
    return "running"


def estimate_cost(model: str, seconds: int) -> float:
    """Upstream-verified per-second pricing (2026-09-06). Unknown models budget high."""
    per_sec = 0.095 if str(model).endswith("turbo") else 0.15
    return per_sec * max(3, min(15, int(seconds)))


class Llm7VideoClient:
    kind = "llm7_video"

    def __init__(self, seat: Dict[str, Any]):
        api = seat.get("api") or {}
        self.host = seat.get("host") or "api.llm7.io"
        self.base = (api.get("base") or DEFAULT_BASE).rstrip("/")
        self.token = api.get("token") or ""
        if not self.token:
            raise SessionExpired("auth", "llm7 seat has no token")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {self.token}"
        self.s.headers["Content-Type"] = "application/json"
        self.s.proxies = {"http": None, "https": None}

    # -- free reads -------------------------------------------------------
    def video_models(self) -> List[Dict[str, Any]]:
        r = self.s.get(f"{self.base}/v1/models", timeout=30)
        if r.status_code == 401:
            raise SessionExpired("auth", "llm7 key dead (invalid_api_key)")
        r.raise_for_status()
        out = []
        for m in r.json().get("data", []):
            if isinstance(m, dict) and m.get("model_type") == "video":
                out.append({"id": m.get("id"), "tier": m.get("tier"),
                            "pricing": (m.get("pricing") or {}).get("price")})
        return out

    def capacity(self) -> Dict[str, Any]:
        try:
            models = self.video_models()
        except Exception as e:
            return {"host": self.host, "error": str(e)[:120]}
        return {"host": self.host, "videoModels": models}

    # -- the gated path ---------------------------------------------------
    def _gate(self, est_cost: float) -> None:
        if not _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND")):
            raise ChatError("wall", "spend gate closed (OMNI_VIDEO_CONFIRM_SPEND unset)")
        cap = float(os.environ.get("OMNI_VIDEO_MAX_SPEND") or 30)
        if est_cost > cap:
            raise ChatError("wall", f"estimated ${est_cost:.3f} exceeds OMNI_VIDEO_MAX_SPEND ${cap:.0f}")

    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        prompt = " ".join(
            str(m.get("content") or "") for m in messages
            if isinstance(m, dict) and m.get("role") != "system").strip()[:2500]
        if not prompt:
            raise ChatError("bad_request", "no prompt text in messages")
        use_model = model or DEFAULT_MODEL
        if str(use_model).startswith("llm7/"):
            use_model = str(use_model).split("/", 1)[1]
        seconds = int(kw.get("seconds") or DEFAULT_SECONDS)
        self._gate(est_cost=estimate_cost(use_model, seconds))

        r = self.s.post(f"{self.base}/v1/videos",
                        json={"model": use_model, "prompt": prompt, "seconds": seconds},
                        timeout=60)
        if r.status_code in (401, 403):
            raise SessionExpired("auth", f"llm7 auth wall (HTTP {r.status_code})")
        if r.status_code == 402 or any(w in (r.text or "").lower() for w in WALL_WORDS):
            raise ChatError("wall", f"llm7 walled (HTTP {r.status_code}): {(r.text or '')[:160]}")
        if r.status_code not in (200, 201, 202):
            raise ChatError(f"HTTP_{r.status_code}", f"submit: {(r.text or '')[:200]}")
        body = r.json()
        job_id = body.get("id") or body.get("task_id") or body.get("job_id")
        if not job_id:
            url = extract_video_url(body)
            if url:
                self._record(use_model, "succeeded", url, 0.0)
                return {"text": url, "label": self.host, "status": "completed",
                        "video_url": url}
            raise ChatError("NO_JOB_ID", f"no job id in submit reply: {json.dumps(body)[:200]}")

        deadline = time.time() + TERMINAL_POLL
        while time.time() < deadline:
            time.sleep(POLL_EVERY)
            p = self.s.get(f"{self.base}/v1/videos/{job_id}", timeout=30)
            if p.status_code in (401, 403):
                raise SessionExpired("auth", f"llm7 auth wall mid-poll (HTTP {p.status_code})")
            if p.status_code >= 400:
                raise ChatError(f"HTTP_{p.status_code}", f"poll: {(p.text or '')[:200]}")
            pb = p.json()
            cls = status_class(pb.get("status"))
            url = extract_video_url(pb)
            if cls == "done" and url:
                self._record(use_model, "succeeded", url, 0.0)
                return {"text": url, "label": self.host, "status": "completed",
                        "video_url": url}
            if cls == "failed":
                raise ChatError("upstream_failed", f"job {job_id} failed: {json.dumps(pb)[:200]}")
        raise ChatError("timeout", f"job {job_id} not terminal in {TERMINAL_POLL}s")

    def _record(self, model: str, status: str, url: str, cost: float) -> None:
        try:
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": time.time(), "model": model, "status": status,
                                     "url": url, "cost_usd": cost}) + "\n")
        except OSError:
            pass


def _selftest() -> int:
    assert extract_video_url({"url": "https://x/y.mp4"}) == "https://x/y.mp4"
    assert extract_video_url({"data": [{"url": "https://x/y.mp4"}]}) == "https://x/y.mp4"
    assert extract_video_url({"result": {"resultUrls": ["https://x/y.mp4"]}}) == "https://x/y.mp4"
    assert extract_video_url({"result": {"resultUrls": ["bad"]}}) == ""
    assert extract_video_url(42) == ""
    assert status_class("success") == "done"
    assert status_class("cancelled") == "failed"
    assert status_class("queuing") == "running"
    assert estimate_cost("kling-v3.0-turbo", 5) == 0.095 * 5
    assert estimate_cost("kling-v3.0-pro", 5) == 0.15 * 5
    assert estimate_cost("unknown", 99) == 0.15 * 15
    print("llm7_video_client selftest: OK (no network)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--capacity", action="store_true")
    ap.add_argument("--seat", default=r"D:\omniroute-monetizer\state\secrets\session_llm7_video.json")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    seat = json.loads(pathlib.Path(a.seat).read_text(encoding="utf-8-sig"))
    c = Llm7VideoClient(seat)
    print(json.dumps(c.capacity(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
