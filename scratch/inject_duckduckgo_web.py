#!/usr/bin/env python3
"""Try duckduckgo-web in OmniRoute with authType=none (no key).
OmniRoute may implement the VQD session flow internally.
Zero-fabrication: only counts LIVE if OmniRoute test returns valid=true.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402


def main():
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
        if (c.get("provider") or "").lower() == "duckduckgo-web":
            target = c
            break

    if target:
        cid = target["id"]
        print(f"[*] existing duckduckgo-web connection {cid}; activating (idempotent)")
        res = api.update_connection(cid, {"isActive": True})
        print(f"[*] PUT -> HTTP {res.get('http_status')}")
    else:
        payload = {
            "provider": "duckduckgo-web",
            "name": "DuckDuckGo Web (keyless)",
            "authType": "none",
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

    # Sync models (may be static list for ddg)
    rs = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
    print(f"[*] sync-models -> HTTP {rs.status_code} {rs.text[:200]}")

    # Live test through OmniRoute
    test = api.test_connection(cid)
    http = test.get("http_status")
    res = test.get("result") or {}
    ok = bool(http == 200 and isinstance(res, dict) and (
        res.get("valid") or res.get("success") or res.get("ok") or res.get("healthy")))
    print(f"[*] test_connection -> HTTP {http} valid={ok} detail={json.dumps(res)[:300]}")

    if ok:
        print(f"[+] DUCKDUCKGO-WEB LIVE IN OMNIROUTE (connection {cid})")
        return 0
    print("[-] OmniRoute test did not return valid=true; NOT counting as live")
    return 5


if __name__ == "__main__":
    sys.exit(main())
