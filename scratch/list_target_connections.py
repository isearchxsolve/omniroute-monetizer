"""List existing OmniRoute connections for the target web-session providers."""
import sys
sys.path.insert(0, ".")
from omniroute_api import OmniRouteAPI

TARGETS = {
    "perplexity-web", "t3-web", "t3-chat-web", "muse-spark-web",
    "blackbox", "blackbox-web", "chatgpt-web", "grok-web",
}

api = OmniRouteAPI()
api.login()
conns = api.get_connections()
print(f"total connections: {len(conns)}")
found = 0
for c in conns:
    prov = c.get("provider")
    if prov in TARGETS:
        found += 1
        key = c.get("apiKey") or ""
        print(
            f"provider={prov!r} id={c.get('id')} authType={c.get('authType')} "
            f"isActive={c.get('isActive')} apiKey_len={len(key)} "
            f"apiKey_prefix={key[:25]!r}"
        )
print(f"matched: {found}")
