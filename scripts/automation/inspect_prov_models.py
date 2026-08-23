"""Inspect model_cache.json and test each healthy provider's flagship models.
"""
from __future__ import annotations
import sys
import json
import time
import pathlib
import requests

sys.stdout.reconfigure(encoding="utf-8")
OMNIROUTE_BASE = "http://localhost:20128"

def log(msg):
    print(msg, flush=True)

def main():
    # 1. Load healthy providers
    fleet_path = pathlib.Path("state/master_probed_fleet.json")
    fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
    healthy_providers = sorted({c["provider"] for c in fleet.get("connections", []) if c.get("valid")})
    log(f"[*] Total healthy providers: {len(healthy_providers)}")
    
    # 2. Load models from model_cache.json or live connections
    cache_path = pathlib.Path("state/model_cache.json")
    prov_models = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            data = cache.get("data", [])
            for item in data:
                mid = item.get("id", "")
                if "/" in mid:
                    p, m = mid.split("/", 1)
                    if p in healthy_providers:
                        prov_models.setdefault(p, []).append(mid)
        except Exception as e:
            log(f"[-] Error loading model cache: {e}")
            
    log(f"[*] Found models in cache for {len(prov_models)} healthy providers.")
    for p in healthy_providers:
        ms = prov_models.get(p, [])
        log(f"  - {p:20}: {len(ms)} models (e.g., {', '.join(ms[:2]) if ms else 'none'})")

if __name__ == "__main__":
    main()
