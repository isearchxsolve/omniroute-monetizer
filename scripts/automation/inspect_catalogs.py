"""Inspect real_model_catalog.json and all_295_providers_catalog.json.
"""
from __future__ import annotations
import json
import pathlib

for fname in ["real_model_catalog.json", "all_295_providers_catalog.json", "exhaustive_frontier_models.json"]:
    p = pathlib.Path("state") / fname
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"=== {fname} ===")
        if isinstance(data, list):
            print(f"List with {len(data)} items, first item: {type(data[0])} {str(data[0])[:120]}")
        elif isinstance(data, dict):
            print(f"Dict with keys: {list(data.keys())[:10]}")
            k0 = list(data.keys())[0]
            print(f"Sample item [{k0}]: {str(data[k0])[:120]}")
