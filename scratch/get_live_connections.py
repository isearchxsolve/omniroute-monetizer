"""Get live OmniRoute connections using the existing auth infrastructure."""
import sys, json
sys.path.insert(0, r'd:\omniroute-monetizer\scripts\automation')
from omniroute_api import OmniRouteAPI, redact

api = OmniRouteAPI()
ok = api.login()
if not ok:
    print("ERROR: Could not authenticate to OmniRoute")
    sys.exit(1)

conns = api.get_connections()
print(f"\n=== Live OmniRoute connections: {len(conns)} ===")
for c in conns:
    cid = c.get('id', '?')[:12]
    prov = c.get('provider', '?')
    active = c.get('isActive', '?')
    auth = c.get('authType', '?')
    has_key = 'yes' if c.get('apiKey') else 'no'
    print(f"  {cid}.. provider={prov} active={active} auth={auth} hasKey={has_key}")

# Save full connection list for reference
with open('state/live_connections_snapshot.json', 'w', encoding='utf-8') as f:
    # Redact API keys before saving
    safe = []
    for c in conns:
        sc = dict(c)
        if sc.get('apiKey'):
            sc['apiKey'] = '[REDACTED]'
        safe.append(sc)
    json.dump({"total": len(conns), "connections": safe}, f, indent=2, ensure_ascii=False)
print(f"\nSnapshot saved to state/live_connections_snapshot.json")
