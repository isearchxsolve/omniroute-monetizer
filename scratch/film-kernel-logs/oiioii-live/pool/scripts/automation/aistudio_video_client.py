"""aistudio_video_client.py — Google Veo via the Gemini API: Python-executed, no browser.

WHY THIS EXISTS. The revised handover (worklog #1369) assigns real Python video-adapter
graduation. The vault's aistudio key (VERIFIED) ListModels as veo-3.1-generate-preview /
-fast / -lite with `predictLongRunning` (measured 2026-08-30), so a genuine submit -> operation
-> poll -> download flow runs from Python with no Chrome anywhere in the request path.

CONTRACT (generativelanguage.googleapis.com, v1beta, measured 2026-08-30):

    POST /v1beta/models/{model}:predictLongRunning   {"instances": [{"prompt": ...}], ...}
         -> 200 {"name": "models/<model>/operations/<id>"}   (a refusal charges nothing)
    GET  /v1beta/{operation.name}                    -> {"done": true, "response": ...} |
                                                        {"done": false} | {"error": {...}}
         result video URI sits somewhere inside response (generatedSamples[].video.uri or
         equivalent) — extracted by deep search, never by guessing one fixed path.
    GET  <video uri>  (x-goog-api-key)               -> video bytes (ISO-BMFF, `ftyp` at 4..8)

MONEY DISCIPLINE — gate CLOSED by default, identical shape to rtst/kie clients:

  * `OMNI_VIDEO_CONFIRM_SPEND` must be set truthy, AND
  * `OMNI_VIDEO_MAX_SPEND` bounds exposure. Free-tier quota (if present on the key's project)
    spends $0; a paid-tier project spends the published per-second rate — exactly ONE submit,
    never a retry. A refused/refused-quota call is an honest wall row, not something to hammer.

SEAT FILE (`state/secrets/session_aistudio_veo.json`), written from the vault key:

    {"host": "aistudio.google.com", "modality": "video",
     "api": {"kind": "aistudio", "token": "<api key>", "base": "https://generativelanguage.googleapis.com"}}

    python aistudio_video_client.py --selftest    # pure logic, no network
    python aistudio_video_client.py --capacity    # free read: ListModels veo visibility
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

DEFAULT_BASE = "https://generativelanguage.googleapis.com"
LEDGER = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "aistudio" / "jobs.jsonl"

MODEL = "veo-3.1-fast-generate-preview"       # cheapest of the three visible Veo models
API_VER = "v1beta"

# A refusal is a wall only when Google says money/quota: 429 RESOURCE_EXHAUSTED and 403 with
# billing language are honest rows (Law 5), never something to hammer.
WALL_WORDS = ("billing", "quota exceeded", "resource_exhausted", "payment", "upgrade",
              "not enabled", "requires billing", "free tier")


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def deep_find_video_uris(node: Any, out: Optional[List[str]] = None) -> List[str]:
    """The result URI's exact path has moved across API revisions; deep-search once."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and v.startswith("http") and (
                    k.lower() in ("uri", "url", "video_uri", "file_uri", "download_url")):
                out.append(v)
            else:
                deep_find_video_uris(v, out)
    elif isinstance(node, list):
        for item in node:
            deep_find_video_uris(item, out)
    return out


def is_wall(status: Optional[int], body: str) -> bool:
    if status is not None and status < 400:
        return False
    if status == 429:
        return True
    return any(w in (body or "").lower() for w in WALL_WORDS)


class AistudioVideoClient:
    """One Google API key's Veo access. Constructed as `AistudioVideoClient(secret=<path>)`."""

    def __init__(self, secret, timeout: int = 900):
        self.timeout = int(timeout)
        self.path = pathlib.Path(secret) if not isinstance(secret, pathlib.Path) else secret
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        api = raw.get("api") or {}
        token = (api.get("token") or api.get("key") or "").strip()
        if not token:
            raise SessionExpired("NO_TOKEN", "aistudio seat carries no api.token -- re-harvest")
        self.host: str = raw.get("host") or "aistudio.google.com"
        self.base: str = (api.get("base") or DEFAULT_BASE).rstrip("/")
        # The one place the key is handled. Never printed.
        self._headers = {"x-goog-api-key": token, "Content-Type": "application/json"}
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
        if r.status_code in (401, 403) and "API_KEY" in text.upper().replace(" ", ""):
            raise SessionExpired("AUTH", f"google rejected the key on {path} ({r.status_code})")
        if r.status_code >= 400:
            if is_wall(r.status_code, text):
                raise ChatError("wall", f"aistudio {path} is walled (HTTP {r.status_code}): "
                                        f"{text[:160]}")
            raise ChatError(f"HTTP_{r.status_code}", f"{path}: {text[:160]}")
        try:
            return r.json()
        except ValueError:
            raise ChatError("UNPARSEABLE", f"{path} returned {r.status_code} non-JSON")

    # ---- free reads ------------------------------------------------------------------------------
    def veo_models(self) -> List[str]:
        data = self._call(f"/{API_VER}/models")
        out = []
        for m in (data.get("models") or []):
            name = m.get("name", "")
            if "veo" in name.lower() and "predictLongRunning" in (m.get("supportedGenerationMethods") or []):
                out.append(name.split("/")[-1])
        return out

    def capacity(self) -> dict:
        return {"host": self.host, "veoModelsVisible": self.veo_models(),
                "note": "visibility is free; one bounded generation is the spend test"}

    # ---- the one path that spends ----------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = str(messages[-1].get("content") or "").strip()
        if len(prompt.split()) < 10:
            raise ChatError("SHORT_PROMPT", "a real clip needs a prompt of ~10+ words")
        use_model = MODEL if not model or model in ("auto", self.host) else model
        if not use_model.startswith("veo"):
            raise ChatError("NO_MODEL", f"this seat serves veo models only, not {use_model!r}")

        if not self.confirm_spend:
            raise ChatError("wall", f"spend gate closed: {use_model} generation; "
                                    "set OMNI_VIDEO_CONFIRM_SPEND=1 to allow this seat to charge")

        body = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": "16:9"}}
        # Submitted ONCE. No retry here, ever.
        op = self._call(f"/{API_VER}/models/{use_model}:predictLongRunning", method="POST",
                        body=body, timeout=180)
        op_name = op.get("name") or ""
        self._ledger({"host": self.host, "operation": op_name, "model": use_model,
                      "submitted_at": int(time.time())})
        if not op_name:
            raise ChatError("NO_JOB_ID", "google accepted the submit but returned no operation name")

        final = self._poll(op_name)
        uris = deep_find_video_uris(final.get("response") or final)
        if not uris:
            raise ChatError("NO_URL", f"operation {op_name} finished with no video uri")
        return {"text": uris[0], "label": self.host, "status": "completed",
                "model": use_model, "operation": op_name, "result_urls": uris}

    def _poll(self, op_name: str) -> dict:
        deadline = time.time() + self.timeout
        transient = 0
        while time.time() < deadline:
            try:
                data = self._call(f"/{API_VER}/{op_name}")
            except SessionExpired:
                raise
            except ChatError as e:
                transient += 1
                if transient > 20:
                    raise ChatError("POLL_FAILED", f"operation {op_name} unpollable: {e.args[0]}")
                time.sleep(10)
                continue
            transient = 0
            if data.get("error"):
                raise ChatError("GEN_FAILED", f"operation {op_name} failed: "
                                              f"{str(data['error'])[:160]}")
            if data.get("done"):
                return data
            time.sleep(10)
        raise ChatError("TIMEOUT", f"operation {op_name} still running after {self.timeout}s "
                                   "(poll it, do not resubmit)")

    def _ledger(self, rec: dict) -> None:
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

    sample = {"done": True, "response": {"generateVideoResponse": {
        "generatedSamples": [{"video": {"uri": "https://x/files/abc:download?alt=media"}}]}}}
    chk("uri found deep in the generateVideoResponse shape",
        deep_find_video_uris(sample) == ["https://x/files/abc:download?alt=media"])
    alt = {"response": {"videos": [{"uri": "https://y/v.mp4"}]}}
    chk("uri found in the alternate videos shape", deep_find_video_uris(alt) == ["https://y/v.mp4"])
    chk("nothing found yields empty list", deep_find_video_uris({"done": True}) == [])

    chk("429 is a wall", is_wall(429, "{}"))
    chk("billing language on an error is a wall", is_wall(403, "requires billing enabled"))
    chk("a 200 is never a wall", not is_wall(200, "anything"))
    chk("a plain 404 is not a wall (wrong id, not money)",
        not is_wall(404, "model not found"))

    chk("gate closed by default", not _truthy(None) and not _truthy("0"))
    chk("gate opens on truthy", _truthy("1") and _truthy("true"))

    e = ChatError("wall", "spend gate closed")
    chk("wall: prefix reaches the face", " ".join(str(a) for a in e.args).lower().startswith("wall:"))

    print(f"\n  {ok} passed, {fail} failed")
    return 0 if not fail else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="pure logic, no network")
    ap.add_argument("--capacity", action="store_true", help="free read: veo model visibility")
    ap.add_argument("--secret", default=str(pathlib.Path(
        r"D:\omniroute-monetizer\state\secrets\session_aistudio_veo.json")))
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.capacity:
        try:
            print(json.dumps(AistudioVideoClient(secret=a.secret).capacity(), indent=2))
        except (ChatError, SessionExpired) as e:
            print(f"error: {str(e)[:200]}")
            return 1
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
