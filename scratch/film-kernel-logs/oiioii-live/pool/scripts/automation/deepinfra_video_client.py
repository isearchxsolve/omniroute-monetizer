"""deepinfra_video_client.py — DeepInfra direct video seat: POST /v1/inference/{model}.

WHY THIS EXISTS. Upstream-verified 2026-09-06 (worklog #1675): DeepInfra's public
/v1/openai/models lists google/veo-3.1 ($0.40/output-sec), google/veo-3.1-fast ($0.15),
Wan-AI/Wan2.6-T2V ($0.10) and PrunaAI/p-video ($0.02), all tags=['video-gen'] — while the
INSTALLED OmniRoute native registry chunk predates these ids (it serves only Wan2.2 x2,
Wan2.7-T2V, LTX-2.3). The native route therefore needs a registry patch + restart
(operator-gated). This client reaches the SAME models DIRECTLY over the documented
DeepInfra inference API, needing only a fresh key — no restart of anything.

CONTRACT (documented by DeepInfra; UNVERIFIED for the video ids until a key proves it):

    POST https://api.deepinfra.com/v1/inference/{model}
         Authorization: Bearer <key>
         {"prompt": "...", optional model params}
         -> 200 {"output": [ ... url(s) ... ]} or {"video_url": ...} (async models
            may return {"request_id"} + status endpoint — extraction tolerates both)
    GET https://api.deepinfra.com/v1/openai/models  (public list, free)

MONEY DISCIPLINE — identical to kie_video_client (gate CLOSED by default):
  * `OMNI_VIDEO_CONFIRM_SPEND` truthy AND `OMNI_VIDEO_MAX_SPEND` (default 30) must
    exceed the estimated per-clip cost (per-output-SECOND pricing measured upstream).
    One bounded generation per graduation run; submit exactly once, no retries.

SEAT FILE (`state/secrets/session_deepinfra_video.json`), written from a fresh vault key:

    {"host": "api.deepinfra.com", "modality": "video",
     "api": {"kind": "deepinfra_video", "token": "<api key>",
             "base": "https://api.deepinfra.com"}}

MODELS (upstream-verified video-gen ids, 2026-09-06):
    google/veo-3.1          $0.40/output-sec
    google/veo-3.1-fast     $0.15/output-sec
    Wan-AI/Wan2.6-T2V       $0.10/output-sec
    PrunaAI/p-video         $0.02/output-sec   (NEW discovery, 1080p48fps)

SECRETS. The key lives only in the seat file and Authorization header; never printed,
logged, or returned.

    python deepinfra_video_client.py --selftest      # pure logic, no network
    python deepinfra_video_client.py --capacity      # free: public model list + tag check
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

DEFAULT_BASE = "https://api.deepinfra.com"
LEDGER = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "deepinfra" / "jobs.jsonl"

# cheapest bounded real generation: p-video at $0.02/s, 5s = $0.10
DEFAULT_MODEL = "PrunaAI/p-video"
DEFAULT_SECONDS = 5
TERMINAL_POLL = 1800
POLL_EVERY = 10.0

WALL_WORDS = ("insufficient", "not enough credit", "out of credit", "no credit",
              "payment required", "quota exceeded", "billing")

# per-output-second pricing measured from the public list (metadata.pricing.output_seconds)
PRICING = {
    "google/veo-3.1": 0.40,
    "google/veo-3.1-fast": 0.15,
    "Wan-AI/Wan2.6-T2V": 0.10,
    "PrunaAI/p-video": 0.02,
}


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def extract_video_url(body: Any) -> str:
    """Tolerant extraction across deepinfra sync shapes. Pure logic, testable."""
    if not isinstance(body, dict):
        return ""
    for key in ("video_url", "url"):
        v = body.get(key)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    out = body.get("output")
    if isinstance(out, list):
        for item in out:
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                return item
            if isinstance(item, dict):
                for key in ("url", "video_url"):
                    v = item.get(key)
                    if isinstance(v, str) and v.startswith(("http://", "https://")):
                        return v
    if isinstance(out, str) and out.startswith(("http://", "https://")):
        return out
    if isinstance(out, dict):
        return extract_video_url(out)
    return ""


def status_class(state: Any) -> str:
    s = str(state or "").strip().lower()
    if s in ("completed", "succeeded", "success"):
        return "done"
    if s in ("failed", "error", "cancelled"):
        return "failed"
    return "running"


def estimate_cost(model: str, seconds: int) -> float:
    per_sec = PRICING.get(model, 0.40)
    return per_sec * max(1, int(seconds))


class DeepInfraVideoClient:
    kind = "deepinfra_video"

    def __init__(self, seat: Dict[str, Any]):
        api = seat.get("api") or {}
        self.host = seat.get("host") or "api.deepinfra.com"
        self.base = (api.get("base") or DEFAULT_BASE).rstrip("/")
        self.token = api.get("token") or ""
        if not self.token:
            raise SessionExpired("auth", "deepinfra seat has no token")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {self.token}"
        self.s.headers["Content-Type"] = "application/json"
        self.s.proxies = {"http": None, "https": None}

    # -- free reads -------------------------------------------------------
    def video_models(self) -> List[Dict[str, Any]]:
        """Public list (works with or without a valid key); tag-verified video-gen only."""
        r = self.s.get(f"{self.base}/v1/openai/models", timeout=30)
        r.raise_for_status()
        out = []
        for m in r.json().get("data", []):
            meta = m.get("metadata") or {}
            if "video-gen" in (meta.get("tags") or []):
                out.append({"id": m.get("id"),
                            "usd_per_output_sec": (meta.get("pricing") or {}).get("output_seconds")})
        return out

    def capacity(self) -> Dict[str, Any]:
        try:
            models = self.video_models()
        except Exception as e:
            return {"host": self.host, "error": str(e)[:120]}
        key_ok = None
        try:
            r = self.s.get(f"{self.base}/v1/openai/models", timeout=30)
            key_ok = r.status_code == 200
        except Exception:
            key_ok = False
        return {"host": self.host, "videoGenModels": len(models), "models": models[:12],
                "keyAccepted": key_ok}

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
            if isinstance(m, dict) and m.get("role") != "system").strip()
        if not prompt:
            raise ChatError("bad_request", "no prompt text in messages")
        use_model = model or DEFAULT_MODEL
        if str(use_model).startswith("deepinfra/"):
            use_model = str(use_model).split("/", 1)[1]
        seconds = int(kw.get("seconds") or DEFAULT_SECONDS)
        self._gate(est_cost=estimate_cost(use_model, seconds))

        r = self.s.post(f"{self.base}/v1/inference/{use_model}",
                        json={"prompt": prompt}, timeout=120)
        if r.status_code in (401, 403):
            raise SessionExpired("auth", f"deepinfra auth wall (HTTP {r.status_code})")
        if r.status_code == 402 or any(w in (r.text or "").lower() for w in WALL_WORDS):
            raise ChatError("wall", f"deepinfra walled (HTTP {r.status_code}): {(r.text or '')[:160]}")
        if r.status_code not in (200, 201, 202):
            raise ChatError(f"HTTP_{r.status_code}", f"submit: {(r.text or '')[:200]}")
        body = r.json()
        url = extract_video_url(body)
        if url:
            self._record(use_model, "succeeded", url, 0.0)
            return {"text": url, "label": self.host, "status": "completed", "video_url": url}
        job_id = body.get("request_id") or body.get("id") or body.get("task_id")
        if not job_id:
            raise ChatError("NO_URL_NO_ID", f"no url/job id: {json.dumps(body)[:200]}")

        deadline = time.time() + TERMINAL_POLL
        while time.time() < deadline:
            time.sleep(POLL_EVERY)
            p = self.s.get(f"{self.base}/v1/inference/request/{job_id}", timeout=30)
            if p.status_code in (401, 403):
                raise SessionExpired("auth", f"deepinfra auth wall mid-poll (HTTP {p.status_code})")
            if p.status_code >= 400:
                raise ChatError(f"HTTP_{p.status_code}", f"poll: {(p.text or '')[:200]}")
            pb = p.json()
            cls = status_class(pb.get("status"))
            url = extract_video_url(pb)
            if cls == "done" and url:
                self._record(use_model, "succeeded", url, 0.0)
                return {"text": url, "label": self.host, "status": "completed", "video_url": url}
            if cls == "failed":
                raise ChatError("upstream_failed", f"request {job_id} failed: {json.dumps(pb)[:200]}")
        raise ChatError("timeout", f"request {job_id} not terminal in {TERMINAL_POLL}s")

    def _record(self, model: str, status: str, url: str, cost: float) -> None:
        try:
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": time.time(), "model": model, "status": status,
                                     "url": url, "cost_usd": cost}) + "\n")
        except OSError:
            pass


def _selftest() -> int:
    assert extract_video_url({"output": ["https://x/y.mp4"]}) == "https://x/y.mp4"
    assert extract_video_url({"output": [{"url": "https://x/y.mp4"}]}) == "https://x/y.mp4"
    assert extract_video_url({"output": "https://x/y.mp4"}) == "https://x/y.mp4"
    assert extract_video_url({"video_url": "https://x/y.mp4"}) == "https://x/y.mp4"
    assert extract_video_url({"output": {"url": "https://x/y.mp4"}}) == "https://x/y.mp4"
    assert extract_video_url({"output": []}) == ""
    assert extract_video_url(None) == ""
    assert status_class("Completed") == "done"
    assert status_class("in_progress") == "running"
    assert estimate_cost("PrunaAI/p-video", 5) == 0.10
    assert estimate_cost("google/veo-3.1", 5) == 2.0
    assert estimate_cost("unknown", 1) == 0.40
    print("deepinfra_video_client selftest: OK (no network)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--capacity", action="store_true")
    ap.add_argument("--seat", default=r"D:\omniroute-monetizer\state\secrets\session_deepinfra_video.json")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    seat = json.loads(pathlib.Path(a.seat).read_text(encoding="utf-8-sig"))
    c = DeepInfraVideoClient(seat)
    print(json.dumps(c.capacity(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
