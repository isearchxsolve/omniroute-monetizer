"""Controlled experiment: is the Gemini 401 caused by the transport swap or by injection?

Four combinations, same URL/headers/cookies:
  A: recorded body  via curl_cffi  (new transport)
  B: injected body  via curl_cffi  (new transport)
  C: recorded body  via requests   (old transport)
  D: injected body  via requests   (old transport)

If B=401 but D=200 -> the transport swap regressed Gemini injection.
If B=401 and D=401 -> injection was already broken; the earlier REPLAY_OK came
                      from another path (needs separate explanation).
"""
import json, sys, urllib.parse
sys.path.insert(0, "scripts/automation")
from pathlib import Path
import requests as req
from curl_cffi import requests as ccreq
from universal_replay import UniversalSessionClient

path = Path("state/secrets/session_google_gemini_web.json")
data = json.loads(path.read_text(encoding="utf-8"))
ex = data["recorded_exchange"]
url, method = ex["url"], ex.get("method", "POST")
headers = dict(ex.get("request_headers") or {})
cookie = ex.get("cookie_header") or data.get("cookie_header") or ""
if cookie:
    headers["Cookie"] = cookie
recorded_body = ex.get("request_body") or ""

client = UniversalSessionClient(path)
new_prompt = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
injected_body = client._inject_prompt(new_prompt)
print("injected differs from recorded?", injected_body != recorded_body)

def fire(label, transport, body):
    h = dict(headers)
    try:
        if transport == "curl_cffi":
            r = ccreq.request(method, url, headers=h, content=body.encode("utf-8"),
                              impersonate="chrome", default_headers=False,
                              allow_redirects=True, timeout=30)
            sc, txt = r.status_code, r.text
        else:
            r = req.request(method, url, headers=h, data=body.encode("utf-8"),
                            allow_redirects=True, timeout=30)
            sc, txt = r.status_code, r.text
        low = txt.lower()
        has_answer = "omni" in low or "the holy cow" in low
        is_401_frame = '"er"' in txt[:200] or ",401," in txt[:300]
        print(f"  {label:32s} status={sc} len={len(txt):6d} "
              f"answer={'YES' if has_answer else 'no '} 401frame={'YES' if is_401_frame else 'no '}")
        return sc, txt
    except Exception as e:
        print(f"  {label:32s} EXC {type(e).__name__}: {str(e)[:80]}")
        return None, ""

print("\n--- recorded body (byte-for-byte) ---")
fire("A recorded/curl_cffi", "curl_cffi", recorded_body)
fire("C recorded/requests ", "requests", recorded_body)
print("\n--- injected body (prompt swapped) ---")
fire("B injected/curl_cffi", "curl_cffi", injected_body)
fire("D injected/requests ", "requests", injected_body)
