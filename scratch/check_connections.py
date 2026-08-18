"""Check existing OmniRoute connections for target providers."""
import sys
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

pw = resolve_password()
print("pw resolved:", bool(pw))
api = OmniRouteAPI(password=pw)
ok = api.login()
print("login ok:", ok)
if ok:
    conns = api.get_connections()
    print(f"total connections: {len(conns)}")
    targets = ["perplexity", "t3", "blackbox", "muse", "spark"]
    for c in conns:
        p = (c.get("provider") or "").lower()
        if any(t in p for t in targets):
            print(f'  {c["id"][:8]} provider={p} authType={c.get("authType")} active={c.get("isActive")} testStatus={c.get("testStatus","?")}')