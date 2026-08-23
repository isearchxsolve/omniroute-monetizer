"""Is OmniRoute's Google Flow 404 a WRONG-PATH problem or a TOKEN-SCOPE problem?

OmniRoute submitted to https://aisandbox-pa.googleapis.com/v1:generateVideo with the antigravity
connection's OAuth token and got HTTP 404 with an HTML body. That HTML (not JSON) strongly suggests
the request never reached a real API method -- a scope/auth rejection from a googleapis endpoint is
normally a JSON error, while a 404 HTML page is what you get for a path the frontend doesn't route.

This probes the SAME host/path directly with the harvested Flow web token to classify the failure:
  - 404 + HTML  -> the path /v1:generateVideo is wrong/stale for this host; fix is the endpoint.
  - 401/403 + JSON -> the token lacks scope for aisandbox; fix is the credential.
  - anything else -> reported verbatim.

It also probes a couple of plausible current shapes so we learn the real path in one pass. Minimal
body on purpose: we are classifying the error, not trying to render (a bad body 400s before work).

SECRETS: token read from the gitignored harvest file; only len+last4 printed; response bodies are
truncated and scanned only for html-vs-json and any error message.
"""
from __future__ import annotations

import json
import pathlib

import requests

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
KEYS = ROOT / "state" / "generated_keys.json"

gf = json.loads(KEYS.read_text(encoding="utf-8")).get("googleflow") or {}
tok = gf.get("key")
if not tok:
    raise SystemExit("no harvested googleflow token")
print(f"token: len={len(tok)}, ends ...{tok[-4:]}  (Flow web session token)")
print()

HOST = "https://aisandbox-pa.googleapis.com"
CANDIDATES = [
    ("POST", f"{HOST}/v1:generateVideo"),
    ("POST", f"{HOST}/v1/video:batchAsyncGenerate"),
    ("POST", f"{HOST}/v1/video:generate"),
    ("GET",  f"{HOST}/v1"),
    ("GET",  f"{HOST}/"),
]
HDR = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
BODY = {"model": "veo-3.1-fast-generate", "sampleCount": 1, "project": gf.get("projectId") or "x"}

for method, url in CANDIDATES:
    try:
        r = (requests.post(url, headers=HDR, json=BODY, timeout=30) if method == "POST"
             else requests.get(url, headers=HDR, timeout=30))
    except Exception as exc:
        print(f"  {method:<4} {url}\n       TRANSPORT {type(exc).__name__}")
        continue
    ct = r.headers.get("content-type", "")
    kind = "HTML" if ("html" in ct.lower() or r.text.lstrip().startswith("<")) else "JSON/text"
    print(f"  {method:<4} {url}")
    print(f"       HTTP {r.status_code}  {kind}  ct={ct[:40]}")
    if kind != "HTML":
        print(f"       body: {r.text[:220]}")
    else:
        # pull the <title> if any -- tells us which Google frontend answered
        t = r.text
        i = t.lower().find("<title>")
        if i >= 0:
            print(f"       title: {t[i+7:t.lower().find('</title>', i)][:80]}")
    print()

print("classification:")
print("  a JSON 401/403 anywhere  -> token scope is the blocker (need aisandbox scope)")
print("  only HTML 404s           -> the path is wrong/stale; the real endpoint differs")
print("  a JSON 200/400 on a path -> THAT path is live; OmniRoute's registry should use it")
