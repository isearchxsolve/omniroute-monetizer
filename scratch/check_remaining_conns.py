import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()
conns = api.get_connections()

targets = ["adapta-web","chatgpt-web","codebuddy-cn","grok-web",
           "microsoft-designer-web","suno","udio","veoaifree-web",
           "yuanbao-web","zed-hosted"]

print(f"total connections: {len(conns)}\n")
found = {}
for c in conns:
    prov = c.get("provider") or ""
    if prov in targets:
        found.setdefault(prov, []).append(c)

for t in targets:
    cs = found.get(t, [])
    if not cs:
        print(f"{t:26s} -> NO CONNECTION")
    else:
        for c in cs:
            key = c.get("apiKey") or ""
            masked = (key[:8] + "..." + str(len(key))) if key else "(empty)"
            print(f"{t:26s} -> id={c.get('id')} active={c.get('isActive')} authType={c.get('authType')} key={masked}")
