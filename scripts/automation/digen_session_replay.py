"""digen_session_replay.py — server-side SESSION REPLAY for digen.ai text-to-video.

Follows the "omni way": replay server-side over plain HTTP using the grabbed 
Digen-* headers. No browser. Safe for parallel dispatch.

    python digen_session_replay.py chat "a red fox running through snow, cinematic"

Spend gate (worklog #1131, matches flow_api_client / rtst_api_client convention):
`OMNI_VIDEO_CONFIRM_SPEND` must be truthy before any submit, else chat() raises.
The shim's bat sets it; direct CLI use without it is refused (safe by default).
"""
from __future__ import annotations
import json
import os
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from veo_session_replay import SessionExpired, ChatError

SECRET = pathlib.Path(r"D:\omniroute-monetizer\state\secrets\session_digen_ai.json")

_DROP_HDR = {"content-length", "accept-encoding", "cookie"}
_TLS = threading.local()

# Estimated credits per 5s clip (video_provider_digen.py convention). Used only for
# read-only capacity(); the real debit happens server-side on submit.
EST_COST_PER_CLIP = 30


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")

def _session() -> requests.Session:
    s = getattr(_TLS, "s", None)
    if s is None:
        s = requests.Session()
        _TLS.s = s
    return s

class DigenSessionClient:
    """Server-side replay client for Digen.ai."""

    def __init__(self, secret: pathlib.Path = SECRET, timeout: int = 120):
        self.secret = secret
        self.timeout = timeout
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))
        self.reload()

    def reload(self) -> None:
        if not self.secret.exists():
            raise ChatError("NO_SESSION", f"no grabbed session at {self.secret}")
        self._data = json.loads(self.secret.read_text(encoding="utf-8"))
        if "recorded_job" not in self._data:
            # Maybe the capture used a different key?
            if "recorded_exchange" in self._data:
                exchanges = [self._data["recorded_exchange"]]
            else:
                raise ChatError("NO_RECORDING", "session file has no recorded_exchange or recorded_job")
        else:
            self._exchanges = self._data["recorded_job"].get("exchanges", [])
            if not self._exchanges:
                raise ChatError("NO_RECORDING", "recorded_job has no exchanges")
            
        # Extract headers from any API exchange
        self._headers = {}
        for ex in self._exchanges:
            h = ex.get("request_headers", {})
            if "Digen-Token" in h:
                for k, v in h.items():
                    if not k.startswith(":") and k.lower() not in _DROP_HDR:
                        self._headers[k] = v
                break
        if not self._headers:
            raise ChatError("NO_HEADERS", "Could not find Digen-Token in recorded exchanges")
            
        self._headers["accept-encoding"] = "gzip, deflate"

    def capacity(self) -> int:
        """Read-only clip capacity: credit/remain // est cost per clip. No spend."""
        try:
            r = requests.get("https://api.digen.ai/v1/credit/remain",
                             headers=self._headers, timeout=15)
            if r.status_code != 200:
                return 0
            bal = (r.json().get("data") or {}).get("remained", 0)
            return int(bal) // EST_COST_PER_CLIP
        except requests.RequestException:
            return 0

    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None, **kw) -> Dict[str, Any]:
        """Submit job, poll until done, return video URL."""
        if not self.confirm_spend:
            raise ChatError(
                "SPEND_GATE_CLOSED",
                "digen submit refused: set OMNI_VIDEO_CONFIRM_SPEND=1 to allow this seat to charge")
        prompt = messages[-1]["content"] if messages else ""
        
        # 1. Submit using the exact captured shape
        submit_url = "https://api.digen.ai/v1/scene/job/submitv1"
        submit_ex = None
        for ex in self._exchanges:
            if "submit" in ex.get("url", ""):
                submit_ex = ex
                break
                
        if not submit_ex:
            raise ChatError("NO_SUBMIT_RECORDING", "No submit exchange found in capture")
            
        tmpl = json.loads(submit_ex["request_body"])
        payload = dict(tmpl)
        if "scene_params" in payload:
            sp = json.loads(payload["scene_params"])
            sp["video_gen_prompt"] = prompt
            payload["scene_params"] = json.dumps(sp)
            
        s = _session()
        try:
            r = s.post(submit_url, headers=self._headers, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise ChatError("NETWORK", str(e)[:200])
            
        if r.status_code in (401, 403):
            raise SessionExpired("HTTP", "session no longer authenticates", status=r.status_code)
        if r.status_code != 200:
            raise ChatError("HTTP", r.text[:300], status=r.status_code)
            
        res = r.json()
        if res.get("errCode") != 0:
            raise ChatError("API_ERROR", res.get("errMsg", "Unknown error"), status=200)
            
        queue_id = res.get("data", {}).get("queueId")
        if not queue_id:
            raise ChatError("API_ERROR", "No queueId returned from submit", status=200)

        # 2. Poll
        poll_url = "https://api.digen.ai/v1/queue/list?page=0&pageSize=10&status=3"
        start_t = time.time()
        
        while time.time() - start_t < self.timeout:
            time.sleep(5)
            try:
                pr = s.get(poll_url, headers=self._headers, timeout=10)
                if pr.status_code == 200:
                    pres = pr.json()
                    jobs = pres.get("data", {}).get("list", [])
                    for job in jobs:
                        if str(job.get("id")) == str(queue_id) or str(job.get("jobId")) == str(queue_id):
                            if job.get("status") == 3:
                                video_url = job.get("videoUrl") or job.get("videoURLV1")
                                return {
                                    "text": video_url,
                                    "model": payload["model"],
                                    "label": payload["model"],
                                    "status": 200,
                                    "frames": 1,
                                    "raw_len": len(pr.text)
                                }
            except requests.RequestException:
                pass # retry on network blip
                
        raise ChatError("TIMEOUT", f"Timed out waiting for video (queueId={queue_id})")

def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--secret", default=str(SECRET))
    sub = ap.add_subparsers(dest="cmd", required=True)
    
    s = sub.add_parser("chat")
    s.add_argument("prompt")
    s.add_argument("--model", default="wan")
    
    c = sub.add_parser("credit")
    
    a = ap.parse_args()
    client = DigenSessionClient(secret=pathlib.Path(a.secret))
    
    if a.cmd == "credit":
        url = "https://api.digen.ai/v1/credit/remain"
        r = requests.get(url, headers=client._headers)
        print(r.json())
        return 0
        
    if a.cmd == "chat":
        r = client.chat([{"role": "user", "content": a.prompt}], model=a.model)
        print(r["text"])
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(_cli())
