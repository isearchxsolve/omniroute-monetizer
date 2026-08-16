#!/usr/bin/env python3
"""Inject the verified Groq key into OmniRoute (zero-fabrication: only after
upstream 200 OK, which scratch/harvest_groq_key.py just confirmed).

Steps:
  1. Load key from state/generated_keys.json (must be verified=full)
  2. POST /api/providers {provider: groq, authType: apikey, apiKey}
     (idempotent: if a groq apikey connection exists, PUT the key instead)
  3. POST /api/providers/{id}/sync-models
  4. POST /api/providers/{id}/test  -> require valid=true
T11-safe: masked key output only.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def main():
    data = json.load(open(KEYS_FILE, encoding="utf-8"))
    entry = data.get("groq")
    if not entry or not entry.get("key"):
        print("[-] no groq key in generated_keys.json")
        return 1
    if entry.get("verified") != "full":
        print(f"[-] refusing to inject: key verified={entry.get('verified')} (need 'full')")
        return 2
    key = entry["key"]
    print(f"[*] injecting verified key {mask(key)} into OmniRoute ...")

    pw = resolve_password()
    if not pw:
        print("[-] no OmniRoute management password resolvable")
        return 3
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return 3

    conns = api.get_connections()
    target = None
    for c in conns:
        if (c.get("provider") or "").lower() == "groq" and c.get("authType") == "apikey":
            target = c
            break

    if target:
        cid = target["id"]
        print(f"[*] existing groq apikey connection {cid}; updating key (idempotent)")
        res = api.update_connection(cid, {"apiKey": key, "isActive": True})
        print(f"[*] PUT -> HTTP {res.get('http_status')}")
    else:
        payload = {
            "provider": "groq",
            "name": "Groq (console, autonomous harvest)",
            "authType": "apikey",
            "apiKey": key,
            "isActive": True,
        }
        r = api.session.post(f"{api.api}/providers", json=payload, timeout=20)
        print(f"[*] POST /api/providers -> HTTP {r.status_code}")
        if r.status_code not in (200, 201):
            print(f"[-] create failed: {r.text[:300]}")
            return 4
        body = r.json()
        cid = body.get("id") or (body.get("connection") or {}).get("id")
        if not cid:
            print(f"[-] no connection id in response: {json.dumps(body)[:300]}")
            return 4
        print(f"[+] created connection {cid}")

    # Sync models
    rs = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
    print(f"[*] sync-models -> HTTP {rs.status_code}")

    # Live test through OmniRoute
    test = api.test_connection(cid)
    http = test.get("http_status")
    res = test.get("result") or {}
    ok = bool(http == 200 and isinstance(res, dict) and (
        res.get("valid") or res.get("success") or res.get("ok") or res.get("healthy")))
    print(f"[*] test_connection -> HTTP {http} valid={ok} detail={json.dumps(res)[:250]}")

    if ok:
        print(f"[+] GROQ LIVE IN OMNIROUTE (connection {cid})")
        return 0
    print("[-] OmniRoute test did not return valid=true; NOT counting as live")
    return 5


if __name__ == "__main__":
    sys.exit(main())
