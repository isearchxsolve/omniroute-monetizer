import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

conns = api.get_connections()
print(f"total connections: {len(conns)}")
# Show any noAuth-ish / mimocode / duckduckgo connections
for c in conns:
    p = c.get("provider", "")
    if p in ("mimocode", "duckduckgo-web", "veoaifree-web", "huggingchat", "zai-web", "zenmux-free", "lmarena"):
        print(f"  {p}: id={c.get('id')} authType={c.get('authType')} active={c.get('isActive')} status={c.get('testStatus')}")

print("\n--- try model variants for mimocode ---")
for m in ["mimocode/mimo-auto", "mimocode/mimo-v2.5", "mimocode/mimo-v2.5-pro", "mimo-auto"]:
    try:
        r = api.session.post(api.v1 + "/chat/completions",
            json={"model": m, "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                  "max_tokens": 60, "stream": False}, timeout=90)
        print(f"  {m}: {r.status_code} {r.text[:160]}")
    except Exception as e:
        print(f"  {m}: EXC {e}")
