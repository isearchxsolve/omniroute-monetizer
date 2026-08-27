"""Diagnose the two regressions (gemini AUTH, felo EMPTY) under curl_cffi.

Fires the EXACT recorded request for each, dumps status, redirect chain,
response headers of interest, and the first chunk of the body so we can tell
credential-death from transport-caused breakage. Read-only against providers.
"""
import json, sys
sys.path.insert(0, "scripts/automation")
from pathlib import Path
from curl_cffi import requests as ccreq

SECRETS = Path("state/secrets")
IMPERSONATE = "chrome"

def probe(fname):
    data = json.loads((SECRETS / fname).read_text(encoding="utf-8"))
    ex = data["recorded_exchange"]
    url, method = ex["url"], ex.get("method", "POST")
    headers = dict(ex.get("request_headers") or {})
    cookie = ex.get("cookie_header") or data.get("cookie_header") or ""
    if cookie:
        headers["Cookie"] = cookie
    body = ex.get("request_body")
    print(f"\n===== {data['host']} ({fname}) =====")
    print(f"  {method} {url[:110]}")
    try:
        r = ccreq.request(method, url, headers=headers,
                          content=body.encode("utf-8") if body else None,
                          impersonate=IMPERSONATE, default_headers=False,
                          allow_redirects=True, timeout=30)
    except Exception as e:
        print(f"  EXC {type(e).__name__}: {e}")
        return
    print(f"  status={r.status_code} final_url={str(r.url)[:110]}")
    hist = [str(h.status_code) + " " + str(h.url)[:80] for h in (r.history or [])]
    if hist:
        print("  redirects:", " -> ".join(hist))
    ct = r.headers.get("content-type", "")
    print(f"  content-type={ct}  body_len={len(r.content)}")
    txt = r.text or ""
    print("  body[:600]:", repr(txt[:600]))

for f in ["session_google_gemini_web.json", "session_felo_ai_web.json"]:
    probe(f)
