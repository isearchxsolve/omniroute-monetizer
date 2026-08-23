"""Check models_by_provider for healthy providers in exhaustive_frontier_models.json.
"""
from __future__ import annotations
import json
import pathlib

p = pathlib.Path("state/exhaustive_frontier_models.json")
data = json.loads(p.read_text(encoding="utf-8"))
by_prov = data.get("models_by_provider", {})

fleet_path = pathlib.Path("state/master_probed_fleet.json")
fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
healthy = sorted({c["provider"] for c in fleet.get("connections", []) if c.get("valid")})

print(f"Total providers in exhaustive catalog: {len(by_prov)}")
for hp in healthy:
    ms = by_prov.get(hp, [])
    print(f"  - {hp:20}: {len(ms):3} models | sample: {ms[:2]}")
