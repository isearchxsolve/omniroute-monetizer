"""Enumerate the full model forest available via OmniRoute (local router)."""
import json
import urllib.request

BASE = "http://localhost:20128"
KEY = "sk-2daf4dd6d1e45047-5d97a4-eb7e8d3b"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


# 1. OpenAI-compatible model list
try:
    models = get("/v1/models")
    data = models.get("data", models) if isinstance(models, dict) else models
    ids = sorted(m["id"] if isinstance(m, dict) else str(m) for m in data)
    print(f"/v1/models: {len(ids)} models")
    for i in ids:
        print(" ", i)
except Exception as e:
    print(f"/v1/models failed: {e}")
    ids = []

# 2. Save for later use
with open(r"d:\omniroute-monetizer\state\omniroute_model_forest.json", "w", encoding="utf-8") as f:
    json.dump(ids, f, indent=2)
print(f"\nSaved {len(ids)} model ids to state/omniroute_model_forest.json")
