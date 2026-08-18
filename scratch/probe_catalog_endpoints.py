import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

endpoints = [
    "/api/discovery",
    "/api/free-models",
    "/api/free-tier",
    "/api/free-provider-rankings",
    "/api/provider-models",
    "/api/synced-available-models",
    "/api/provider-stats",
]
for ep in endpoints:
    try:
        r = api.session.get(api.api.replace("/api", "") + ep, timeout=30)
        txt = r.text
        print(f"{ep}: {r.status_code} len={len(txt)}")
        if r.status_code == 200 and len(txt) < 600:
            print("   ", txt[:500])
        elif r.status_code == 200:
            try:
                j = json.loads(txt)
                if isinstance(j, dict):
                    print("    keys:", list(j.keys())[:12])
                elif isinstance(j, list):
                    print("    list len:", len(j), "first:", json.dumps(j[0])[:200] if j else "empty")
            except Exception:
                print("    (not json)", txt[:200])
    except Exception as e:
        print(f"{ep}: EXC {e}")
