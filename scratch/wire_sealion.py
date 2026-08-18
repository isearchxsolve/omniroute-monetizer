"""Wire the SeaLion trial key from browser page-memory into OmniRoute.
The key is held ONLY in the connected Chrome page's window.__omni_sealion_key.
This script reads it through CDP, POSTs to /api/providers {provider:sealion, authType:apikey},
and prints ONLY the HTTP status and returned connection id. Never logs the key.

Wiring-only pass: connection created IS ACTIVE=False; no sync-models, no test.
"""
import sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, r'd:\omniroute-monetizer\scripts\automation')
from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password


def main():
    # 1. Pull the key from the SeaLion tab's browser memory.
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
        ctx = b.contexts[0]
        seats = [p for p in ctx.pages if 'sea-lion.ai/key-manager' in p.url]
        if not seats:
            print('[-] SeaLion key-manager tab not found in connected profile')
            return 1
        page = seats[0]
        key = page.evaluate('() => window.__omni_sealion_key || null')
        b.close()
    if not key:
        print('[-] key not present in browser page memory (window.__omni_sealion_key)')
        return 2
    print(f'[+] key retrieved from browser memory (len={len(key)}, value suppressed)')

    # 2. Authenticate to OmniRoute management.
    pw = resolve_password()
    if not pw:
        print('[-] OmniRoute management password not resolvable')
        return 3
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return 3

    # 3. Idempotency: update an existing sealion apikey connection if present.
    conns = api.get_connections()
    target = next((c for c in conns if (c.get('provider') or '').lower() == 'sealion' and c.get('authType') == 'apikey'), None)
    if target:
        cid = target['id']
        print(f'[*] existing sealion apikey connection {cid[:12]}.. ; updating key (idempotent), active=False')
        res = api.update_connection(cid, {'apiKey': key, 'isActive': False})
        print(f'[*] PUT -> HTTP {res.get("http_status")}')
        # safe connection id only
        print(f'[OK] UPDATE sealion cid={cid} status=inactive_pending_verification')
        return 0

    # 4. Create new connection (inactive per wiring-only pass).
    payload = {
        'provider': 'sealion',
        'name': 'omniroute monetizer',
        'authType': 'apikey',
        'apiKey': key,
        'isActive': False,
    }
    r = api.session.post(f'{api.api}/providers', json=payload, timeout=20)
    print(f'[*] POST /api/providers -> HTTP {r.status_code}')
    if r.status_code not in (200, 201):
        print(f'[-] create failed: {r.text[:300]}')
        return 4
    body = r.json()
    cid = body.get('id') or (body.get('connection') or {}).get('id')
    if not cid:
        print(f'[-] no connection id in response (body suppressed): {bool(body)}')
        return 4
    print(f'[OK] CREATED sealion cid={cid} status=inactive_pending_verification')
    return 0


if __name__ == '__main__':
    sys.exit(main())
