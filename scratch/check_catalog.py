"""Check the OmniRoute provider catalog for the target provider slugs."""
import sys
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

pw = resolve_password()
api = OmniRouteAPI(password=pw)
api.login()

# Try to get the provider catalog
import requests
r = api.session.get(f"{api.api}/providers/catalog", timeout=20)
print(f"catalog HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    providers = data if isinstance(data, list) else data.get("providers", data.get("catalog", []))
    print(f"catalog entries: {len(providers)}")
    targets = ["perplexity", "t3", "blackbox", "muse", "spark"]
    for p in providers:
        slug = (p.get("id") or p.get("slug") or p.get("provider") or "").lower()
        if any(t in slug for t in targets):
            print(f"  slug={slug} name={p.get('name','?')} authType={p.get('authType', p.get('authTypes','?'))} authHeader={p.get('authHeader','?')}")
else:
    print(r.text[:500])