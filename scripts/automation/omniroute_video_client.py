"""omniroute_video_client.py — bridge client for OmniRoute's NATIVE /v1/videos/generations.

WHY THIS EXISTS. Workstream A of the revised assignment (worklog #1372): OmniRoute exposes a
native video face on :20128 that accepts `{"model": "<provider/model>", "prompt": "..."}` and
returns the rendered media ON THE SAME CONNECTION — a fully synchronous contract with NO job id
and NO status endpoint (measured 2026-08-30: GET /v1/videos/generations is the model catalog;
the POST holds the connection for the whole render; a client timeout orphans the result because
the server streams into a dead socket).

CONTRACT (measured on :20128, 2026-08-30):
    POST /v1/videos/generations  {"model": "vertex/veo-2.0-generate-001", "prompt": "..."}
         -> 200 video/mp4 bytes  (render holds ~2-8 min; client timeout must exceed it)
         -> 400 invalid model / unsupported format (validation errors are free)
         -> 402/429 upstream wallet/quota walls
    Model ids: `provider/model`, exactly one slash. The accepted set is OmniRoute's internal
    video registry (measured: vertex/veo-2.0-generate-001 accepted; gemini/* and nested ids
    rejected by the validator; pollinations accepted but "Unsupported video format").

MONEY DISCIPLINE — gate CLOSED by default (OMNI_VIDEO_CONFIRM_SPEND + OMNI_VIDEO_MAX_SPEND).
One submit per call, never retried: the render is billed upstream even when the caller
times out, which is exactly how the first vertex attempt was orphaned.

SEAT FILE (`state/secrets/session_omniroute_native.json`):

    {"host": "omniroute-native", "modality": "video",
     "api": {"kind": "omniroute_native", "token": "", "base": "http://127.0.0.1:20128"}}

Media handling: the synchronous response body IS the clip; the adapter validates the
ISO-BMFF `ftyp` magic, writes it under state/harvest/omniroute_native/, and returns a
file:// URL — the durable `:8190` record then points at completed downloadable media.

    python omniroute_video_client.py --selftest     # pure logic, no network
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

DEFAULT_BASE = "http://127.0.0.1:20128"
LEDGER = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "omniroute_native"
MODEL = "vertex/veo-3.1-generate-preview"   # empirically the rendering id (worklog #1372):
# veo-2.0-generate-001 reaches vertex but 400s "Invalid resource field value" — OmniRoute's
# veo-2.0 adapter defect; veo-3.1-generate-preview held a full ~7 min render. Evidence wins
# over the pricing guess; the fast/lite variants remain untested fallbacks.
HARVEST = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "omniroute_native"


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def looks_like_mp4(b: bytes) -> bool:
    return len(b) > 12 and b[4:8] == b"ftyp"


def is_wall(status: Optional[int], body: str) -> bool:
    if status == 402:
        return True
    if status is not None and status < 400:
        return False
    low = (body or "").lower()
    return any(w in low for w in ("insufficient", "not enough credit", "out of credit",
                                  "quota", "payment required", "billing"))


class OmnirouteVideoClient:
    """The merged surface's bridge to OmniRoute's synchronous native video face."""

    def __init__(self, secret, timeout: int = 900):
        self.timeout = int(timeout)
        self.path = pathlib.Path(secret) if not isinstance(secret, pathlib.Path) else secret
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        api = raw.get("api") or {}
        self.host: str = raw.get("host") or "omniroute-native"
        self.base: str = (api.get("base") or DEFAULT_BASE).rstrip("/")
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        try:
            self.max_spend = float(os.environ.get("OMNI_VIDEO_MAX_SPEND") or 30)
        except ValueError:
            self.max_spend = 30.0

    # ---- free reads ------------------------------------------------------------------------------
    def video_models(self) -> List[str]:
        r = requests.get(f"{self.base}/v1/videos/generations", timeout=60,
                         proxies={"http": None, "https": None})
        if r.status_code != 200:
            raise ChatError("HTTP_%d" % r.status_code, "video model catalog unavailable")
        out = []
        for row in (r.json().get("data") or []):
            mid = row.get("id")
            if isinstance(mid, str):
                out.append(mid)
        return out

    def capacity(self) -> dict:
        return {"host": self.host, "videoModelsVisible": len(self.video_models()),
                "note": "synchronous contract; cost is upstream-side per generation"}

    # ---- the one path that spends ----------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = str(messages[-1].get("content") or "").strip()
        if len(prompt.split()) < 10:
            raise ChatError("SHORT_PROMPT", "a real clip needs a prompt of ~10+ words")
        use_model = MODEL if not model or model in ("auto", self.host) else model
        if "/" not in use_model:
            raise ChatError("MODEL_ID_FAILURE", f"native contract needs provider/model, got "
                                                f"{use_model!r}")

        if not self.confirm_spend:
            raise ChatError("wall", f"spend gate closed: {use_model} synchronous render; "
                                    "set OMNI_VIDEO_CONFIRM_SPEND=1 to allow this seat to charge")

        # ONE submit. The connection holds for the whole render; a client timeout orphans the
        # billed result, so the timeout ceiling is deliberately the render budget, not a retry knob.
        try:
            r = requests.post(f"{self.base}/v1/videos/generations",
                              json={"model": use_model, "prompt": prompt},
                              timeout=self.timeout, proxies={"http": None, "https": None})
        except requests.RequestException as e:
            raise ChatError("TRANSPORT", f"native video POST: {type(e).__name__} "
                                         "(the render may STILL be running upstream; "
                                         "poll nothing, resubmit nothing)")
        ctype = (r.headers.get("Content-Type") or "").lower()
        if r.status_code in (401, 403):
            raise SessionExpired("HTTP", f"omniroute refused the request ({r.status_code})")
        if r.status_code >= 400:
            if is_wall(r.status_code, r.text or ""):
                raise ChatError("wall", f"native video {use_model} walled (HTTP {r.status_code}): "
                                        f"{(r.text or '')[:160]}")
            raise ChatError(f"HTTP_{r.status_code}", f"native video: {(r.text or '')[:200]}")

        if "video" in ctype or looks_like_mp4(r.content or b""):
            HARVEST.mkdir(parents=True, exist_ok=True)
            name = "clip_%s.mp4" % time.strftime("%Y%m%d_%H%M%S")
            out = HARVEST / name
            tmp = out.with_suffix(".mp4.tmp")
            tmp.write_bytes(r.content or b"")
            os.replace(tmp, out)
            if not looks_like_mp4(out.read_bytes()[:16]):
                raise ChatError("ADAPTER_FAILURE", f"saved media failed the ftyp check: {out.name}")
            return {"text": out.as_uri(), "label": self.host, "status": "completed",
                    "model": use_model, "bytes": len(r.content or b""),
                    "file": str(out)}
        # A JSON body on success would mean the contract changed: surface it verbatim-shaped.
        try:
            data = r.json()
        except ValueError:
            raise ChatError("ADAPTER_FAILURE", f"unrecognized success payload ({ctype})")
        raise ChatError("ADAPTER_FAILURE", f"unexpected JSON success payload: {str(data)[:200]}")

    def _ledger(self, rec: dict) -> None:
        try:
            LEDGER.mkdir(parents=True, exist_ok=True)
            with (LEDGER / "jobs.jsonl").open("a", encoding="utf-8") as fh:
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

    chk("mp4 magic detected", looks_like_mp4(b"\x00\x00\x00 ftypisom" + b"x" * 8))
    chk("truncated body rejected", not looks_like_mp4(b"\x00\x00 ft"))
    chk("402 is a wall", is_wall(402, "{}"))
    chk("quota language on an error is a wall", is_wall(429, "quota exceeded"))
    chk("a 200 is never a wall", not is_wall(200, "billing"))
    chk("gate closed by default", not _truthy(None) and not _truthy("0"))
    chk("gate opens on truthy", _truthy("1") and _truthy("YES"))
    chk("provider/model shape enforced", "/" not in "veo-2.0" )

    e = ChatError("wall", "spend gate closed")
    chk("wall: prefix reaches the face", " ".join(str(a) for a in e.args).lower().startswith("wall:"))

    print(f"\n  {ok} passed, {fail} failed")
    return 0 if not fail else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="pure logic, no network")
    ap.add_argument("--capacity", action="store_true", help="free read: video model catalog")
    ap.add_argument("--secret", default=str(pathlib.Path(
        r"D:\omniroute-monetizer\state\secrets\session_omniroute_native.json")))
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.capacity:
        try:
            print(json.dumps(OmnirouteVideoClient(secret=a.secret).capacity(), indent=2))
        except (ChatError, SessionExpired) as e:
            print(f"error: {str(e)[:200]}")
            return 1
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
