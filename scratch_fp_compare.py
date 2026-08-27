"""Study proof: what does a TLS/HTTP2 fingerprint checker see from our two transports?

Compares plain `requests` (what universal_replay uses today) against
`curl_cffi` with impersonate="chrome" (the weapon).
"""
import json

URL = "https://tls.peet.ws/api/all"

def show(tag, d):
    tls = d.get("tls", {})
    h2 = d.get("http2", {})
    ua = d.get("user_agent", "")
    print(f"--- {tag} ---")
    print("  user_agent :", ua[:90])
    print("  ja3        :", tls.get("ja3"))
    print("  ja3_text   :", (tls.get("ja3_text") or "")[:120])
    print("  ja4        :", tls.get("ja4"))
    print("  peetprint  :", (tls.get("peetprint_hash") or "")[:64])
    ak = h2.get("akamai_fingerprint_hash") or h2.get("akamai_hash")
    print("  akamai(h2) :", ak)
    hdrs = d.get("headers", {})
    print("  header keys:", ",".join(list(hdrs.keys())[:14]))
    print()

# 1) plain requests — the current transport
try:
    import requests
    r = requests.get(URL, timeout=30)
    show("requests (current transport)", r.json())
except Exception as e:
    print("requests failed:", e)

# 2) curl_cffi impersonating Chrome — the weapon
try:
    import curl_cffi
    r = curl_cffi.get(URL, impersonate="chrome", timeout=30)
    show("curl_cffi impersonate=chrome", r.json())
except Exception as e:
    print("curl_cffi failed:", e)
