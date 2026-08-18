"""Shallow check: live OmniRoute connection inventory (no secret values printed)."""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI  # type: ignore

def main():
    pw = resolve_password()
    if not pw:
        print("NO_PASSWORD_RESOLVED"); return 1
    api = OmniRouteAPI(password=pw)
    conns = api.get_connections()
    print("len:", len(conns))
    rows = []
    for c in conns:
        rows.append({
            "id": c.get("id"),
            "provider": c.get("provider"),
            "authType": c.get("authType"),
            "isActive": c.get("isActive"),
            "hasKey": bool((c.get("apiKey") or "").strip()),
        })
    rows.sort(key=lambda r: (r["provider"] or ""))
    print(json.dumps(rows, indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
