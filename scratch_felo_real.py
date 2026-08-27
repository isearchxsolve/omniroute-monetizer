"""Test the REAL multistep_replay.felo_followup code path under curl_cffi.

Fires the recorded POST to get a fresh bootstrap, then calls the actual
felo_followup() (no context manager, uses _stream_get + _iter_text_chunks)
to see whether the streaming path delivers the answer.
"""
import json, sys
sys.path.insert(0, "scripts/automation")
from pathlib import Path
from curl_cffi import requests as ccreq
import multistep_replay as ms

print("HAVE_CURL_CFFI:", ms._HAVE_CURL_CFFI)

data = json.loads(Path("state/secrets/session_felo_ai_web.json").read_text(encoding="utf-8"))
ex = data["recorded_exchange"]
headers = dict(ex.get("request_headers") or {})
cookie = ex.get("cookie_header") or data.get("cookie_header") or ""
if cookie:
    headers["Cookie"] = cookie

# Step 1: POST -> bootstrap (through impersonation transport)
r = ccreq.request("POST", ex["url"], headers=headers,
                  content=ex["request_body"].encode("utf-8"),
                  impersonate="chrome", default_headers=False,
                  allow_redirects=True, timeout=30)
print("POST status", r.status_code, "len", len(r.content))
bootstrap_body = r.text

# Step 2: call the REAL followup
answer, err = ms.felo_followup(bootstrap_body, headers, cookie, timeout=60.0)
print("\n=== felo_followup result ===")
print("error:", err)
print("answer len:", len(answer) if answer else 0)
if answer:
    low = answer.lower()
    print("contains holy cow?", "the holy cow" in low)
    print("answer head:", repr(answer[:300]))
    print("answer tail:", repr(answer[-300:]))
