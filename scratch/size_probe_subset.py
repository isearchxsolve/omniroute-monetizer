import sys, json, collections
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

conns = api.get_connections()
print("total connections:", len(conns))
active = [c for c in conns if c.get("isActive")]
print("ACTIVE connections:", len(active))
for c in active:
    print(f"  {c.get('provider'):28s} authType={c.get('authType'):10s} status={c.get('testStatus')} hasKey={bool(c.get('apiKey'))}")

print("\ninactive with credentials:")
for c in conns:
    if not c.get("isActive") and (c.get("apiKey") or c.get("providerSpecificData")):
        psd = c.get("providerSpecificData") or {}
        print(f"  {c.get('provider'):28s} authType={c.get('authType'):10s} status={c.get('testStatus')} hasKey={bool(c.get('apiKey'))} psdKeys={list(psd.keys())[:5]}")
