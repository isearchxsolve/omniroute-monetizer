"""Wire the Nomic key from browser page-memory into OmniRoute.
Key lives only in window.__omni_nomic_key on the Atlas page.
Wiring-only pass: connection created inactive; no sync-models, no test.
"""
import sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, r'd:\omniroute-monetizer\scripts\automation')
from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password


def main():
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
        ctx = b.contexts[0]
        pages = [p for p in ctx.pages if 'atlas.nomic.ai' in p.url]
        if not pages:
            print('[-] Nomic Atlas tab not found')
            return 1
        page = pages[0]
        key = page.evaluate('() => window.__omni_nomic_key || null')
        # close the reveal modal if still open
        try:
            page.get_by_role('button', name='Done').click(timeout=5000)
        except Exception:
            pass
        b.close()
    if not key:
        print('[-] key not in browser page memory')
        return 2
    print(f'[+] key retrieved from browser memory (len={len(key)}, value suppressed)')

    pw_str = resolve_password()
    if not pw_str:
        print('[-] OmniRoute password not resolvable')
        return 3
    api = OmniRouteAPI(password=pw_str)
    if not api.login():
        return 3

    conns = api.get_connections()
    target = next((c for c in conns if (c.get('provider') or '').lower() == 'nomic' and c.get('authType') == 'apikey'), None)
    if target:
        cid = target['id']
        print(f'[*] existing nomic apikey connection {cid[:12]}; updating key (idempotent), active=False')
        res = api.update_connection(cid, {'apiKey': key, 'isActive': False})
        print(f'[*] PUT -> HTTP {res.get("http_status")}')
        print(f'[OK] UPDATE nomic cid={cid}')
        return 0

    payload = {
        'provider': 'nomic',
        'name': 'omniroute-monetizer',
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
        print(f'[-] no cid in response')
        return 4
    print(f'[OK] CREATED nomic cid={cid} status=inactive_pending_verification')
    return 0


if __name__ == '__main__':
    sys.exit(main())
