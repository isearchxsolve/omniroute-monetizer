"""Query live OmniRoute connections and compare with ledger."""
import json, requests, sys

# 1. Live OmniRoute connections
try:
    r = requests.get('http://localhost:20128/api/providers', timeout=10)
    data = r.json()
    conns = data.get('connections', data if isinstance(data, list) else [])
    print(f"=== Live OmniRoute connections: {len(conns)} ===")
    for c in conns:
        cid = c.get('id', '?')[:12]
        prov = c.get('provider', '?')
        active = c.get('isActive', '?')
        auth = c.get('authType', '?')
        has_key = 'yes' if c.get('apiKey') else 'no'
        print(f"  {cid}.. provider={prov} active={active} auth={auth} hasKey={has_key}")
except Exception as e:
    print(f"ERROR querying OmniRoute: {e}")
    conns = []

# 2. Load ledger
d = json.load(open('state/all_296_providers_execution_ledger.json', encoding='utf-8'))
providers = d['providers']

# 3. Wired/live providers
print(f"\n=== LIVE_ACTIVE + WIRED_PENDING_VERIFICATION ===")
wired = {k: v for k, v in providers.items() if v.get('status') in ('LIVE_ACTIVE', 'WIRED_PENDING_VERIFICATION')}
for k in sorted(wired):
    st = wired[k].get('status')
    det = wired[k].get('details', {})
    blocker = det.get('blocker', '')[:80]
    print(f"  {k}: {st} | {blocker}")

# 4. All non-EXTERNAL providers (other blocked categories)
print(f"\n=== BLOCKED_WEB_SESSION ({sum(1 for v in providers.values() if v.get('status')=='BLOCKED_WEB_SESSION')}) ===")
for k in sorted(k2 for k2, v in providers.items() if v.get('status') == 'BLOCKED_WEB_SESSION'):
    v = providers[k]
    obs = v.get('observed_verdict', '')
    note = v.get('note', '')[:100]
    cls = v.get('classification', '')
    print(f"  {k}: verdict={obs} cls={cls} | {note}")

print(f"\n=== BLOCKED_AUTH_REQUIRED ({sum(1 for v in providers.values() if v.get('status')=='BLOCKED_AUTH_REQUIRED')}) ===")
for k in sorted(k2 for k2, v in providers.items() if v.get('status') == 'BLOCKED_AUTH_REQUIRED'):
    v = providers[k]
    det = v.get('details', {})
    blocker = det.get('blocker', '')[:120]
    print(f"  {k}: {blocker}")

print(f"\n=== BLOCKED_CREDITS ({sum(1 for v in providers.values() if v.get('status')=='BLOCKED_CREDITS')}) ===")
for k in sorted(k2 for k2, v in providers.items() if v.get('status') == 'BLOCKED_CREDITS'):
    v = providers[k]
    det = v.get('details', {})
    blocker = det.get('blocker', '')[:120]
    print(f"  {k}: {blocker}")

print(f"\n=== BLOCKED_LOCAL_RUNTIME ({sum(1 for v in providers.values() if v.get('status')=='BLOCKED_LOCAL_RUNTIME')}) ===")
for k in sorted(k2 for k2, v in providers.items() if v.get('status') == 'BLOCKED_LOCAL_RUNTIME'):
    v = providers[k]
    det = v.get('details', {})
    blocker = det.get('blocker', '')[:120]
    print(f"  {k}: {blocker}")

print(f"\n=== NOT_CHAT_COMPLETABLE ({sum(1 for v in providers.values() if v.get('status')=='NOT_CHAT_COMPLETABLE')}) ===")
for k in sorted(k2 for k2, v in providers.items() if v.get('status') == 'NOT_CHAT_COMPLETABLE'):
    v = providers[k]
    det = v.get('details', {})
    blocker = det.get('blocker', '')[:120]
    print(f"  {k}: {blocker}")

print(f"\n=== BLOCKED_UNVERIFIED / BLOCKED_VALIDATION_UNSUPPORTED / BLOCKED_UPSTREAM_DOWN / BLOCKED_FORBIDDEN / BLOCKED_RATE_LIMITED / BLOCKED_ENDPOINT_GONE / AUTHENTICATED_CLOUDFLARE ===")
for k in sorted(k2 for k2, v in providers.items() if v.get('status') in ('BLOCKED_UNVERIFIED', 'BLOCKED_VALIDATION_UNSUPPORTED', 'BLOCKED_UPSTREAM_DOWN', 'BLOCKED_FORBIDDEN', 'BLOCKED_RATE_LIMITED', 'BLOCKED_ENDPOINT_GONE', 'AUTHENTICATED_CLOUDFLARE_TLS_BLOCKED')):
    v = providers[k]
    st = v.get('status')
    det = v.get('details', {})
    blocker = det.get('blocker', '')[:120]
    print(f"  {k}: {st} | {blocker}")
