import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

r = api.session.get(api.api.replace("/api", "") + "/api/synced-available-models", timeout=60)
cat = r.json()
print("providers in live catalog:", len(cat))
sample_key = list(cat.keys())[0]
print("sample entry:", sample_key, "->", json.dumps(cat[sample_key])[:300])

r2 = api.session.get(api.api.replace("/api", "") + "/api/provider-stats", timeout=60)
stats = r2.json()
print("\nprovider-stats keys:", list(stats.keys()))
provs = stats.get("providers")
if isinstance(provs, dict):
    print("stats providers count:", len(provs))
    sk = list(provs.keys())[0]
    print("sample stat:", sk, "->", json.dumps(provs[sk])[:300])
elif isinstance(provs, list):
    print("stats providers list len:", len(provs))
    print("sample:", json.dumps(provs[0])[:300])

# free-provider-rankings
r3 = api.session.get(api.api.replace("/api", "") + "/api/free-provider-rankings", timeout=60)
rank = r3.json()
print("\nrankings sample:", json.dumps(rank.get("rankings", [])[:3])[:400])
