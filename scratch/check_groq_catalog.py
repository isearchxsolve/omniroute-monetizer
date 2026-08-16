#!/usr/bin/env python3
"""Check OmniRoute catalog requirements for groq + sambanova connections."""
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BASE = "http://127.0.0.1:20128"

# resolve mgmt password from DPAPI vault
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))
try:
    from oauth_keepalive import resolve_password
    pw = resolve_password()
except Exception as e:
    print("[-] could not resolve password:", e)
    sys.exit(1)

cj = None
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

req = urllib.request.Request(BASE + "/api/auth/login",
                             data=json.dumps({"password": pw}).encode(),
                             headers={"Content-Type": "application/json"})
r = opener.open(req, timeout=15)
print("[+] login:", r.status)

# get catalog / provider definitions
for path in ["/api/providers/catalog", "/api/provider-catalog", "/api/providers/definitions"]:
    try:
        r = opener.open(BASE + path, timeout=15)
        data = json.loads(r.read().decode())
        print(f"[+] {path} -> {r.status}, type={type(data).__name__}")
        # find groq/sambanova entries
        items = data if isinstance(data, list) else data.get("providers", data.get("catalog", []))
        if isinstance(items, dict):
            items = list(items.values()) if not any(k in items for k in ("groq","sambanova")) else [items[k] for k in ("groq","sambanova") if k in items]
        for it in items:
            if isinstance(it, dict):
                name = str(it.get("id", it.get("slug", it.get("name", "")))).lower()
                if "groq" in name or "sambanova" in name:
                    print(json.dumps(it, indent=1)[:600])
        break
    except Exception as e:
        print(f"[-] {path}: {e}")
