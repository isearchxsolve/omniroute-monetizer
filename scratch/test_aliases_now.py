"""Test the core OmniRoute aliases end-to-end to see what's actually broken."""
import json
import sys
import time

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)

aliases = ["frontier", "auto/best-coding", "auto/best-reasoning", "auto/best-chat", "kimi-coding"]
payload = {
    "model": None,
    "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
    "max_tokens": 20,
    "stream": False,
}

for a in aliases:
    payload["model"] = a
    t0 = time.time()
    try:
        r = s.post(f"{BASE}/v1/chat/completions", json=payload, timeout=60)
        dt = time.time() - t0
        if r.status_code == 200:
            j = r.json()
            content = (j.get("choices") or [{}])[0].get("message", {}).get("content", "")
            model = j.get("model", "")
            print(f"OK   {a:24s} {dt:5.1f}s -> model={model} content={content[:40]!r}")
        else:
            print(f"FAIL {a:24s} {dt:5.1f}s HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"ERR  {a:24s} {time.time()-t0:5.1f}s {type(e).__name__}: {str(e)[:150]}")
