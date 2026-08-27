"""Test the Felo two-step follow-up stream under curl_cffi directly.

POST returns bootstrap {stream_key}; the answer arrives on a GET stream.
This reproduces what multistep_replay.felo_followup does, to see whether the
curl_cffi streaming path actually delivers the answer text.
"""
import json, sys
sys.path.insert(0, "scripts/automation")
from pathlib import Path
from curl_cffi import requests as ccreq

data = json.loads(Path("state/secrets/session_felo_ai_web.json").read_text(encoding="utf-8"))
ex = data["recorded_exchange"]
headers = dict(ex.get("request_headers") or {})
cookie = ex.get("cookie_header") or data.get("cookie_header") or ""
if cookie:
    headers["Cookie"] = cookie

# Step 1: POST -> bootstrap
r = ccreq.request("POST", ex["url"], headers=headers,
                  content=ex["request_body"].encode("utf-8"),
                  impersonate="chrome", default_headers=False,
                  allow_redirects=True, timeout=30)
print("POST status", r.status_code, "len", len(r.content))
boot = r.json()
print("bootstrap keys:", sorted(boot.keys()))
stream_key = boot.get("stream_key")
short_id = boot.get("thread_short_id")
print("stream_key:", stream_key, "short_id:", short_id)

# Step 2: GET the stream. Use the REAL url shape from multistep_replay.felo_followup.
auth = headers.get("Authorization", "")
get_url = f"https://felo.ai/api/message/v1/stream/{stream_key}?offset=0"
gh = {
    "Authorization": auth,
    "User-Agent": headers.get("User-Agent", ""),
    "Referer": f"https://felo.ai/search/{short_id}",
    "Accept": "*/*",
}
if cookie:
    gh["Cookie"] = cookie
print("\nGET", get_url[:120])
got = []
try:
    with ccreq.get(get_url, headers=gh, impersonate="chrome",
                   default_headers=False, stream=True, timeout=60) as sr:
        print("GET status", sr.status_code, "ct", sr.headers.get("content-type"))
        n = 0
        for chunk in sr.iter_content(None, decode_unicode=True):
            if not chunk:
                continue
            got.append(chunk)
            n += len(chunk)
            if n > 40000:
                break
except Exception as e:
    print("GET EXC", type(e).__name__, e)

full = "".join(got)
print("\nstream total bytes:", len(full))
print("contains holy cow?", "the holy cow" in full.lower())
print("stream head:", repr(full[:400]))
print("stream tail:", repr(full[-400:]))
