#!/usr/bin/env python3
"""
Bulk Provider Model Synchronizer & Upstream Health Engine.
Executes POST /api/providers/{id}/sync-models and POST /api/providers/{id}/test
across all active provider connections in OmniRoute.
"""
import sys
import time
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

def run_sync():
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        print("[-] Login failed.")
        return False
    
    conns = api.get_connections()
    print(f"[+] Retrieved {len(conns)} provider connections from OmniRoute.")
    
    results = []
    
    for c in conns:
        cid = c.get("id")
        pname = c.get("provider")
        is_active = c.get("isActive", False)
        
        if not is_active:
            continue
            
        print(f"\n[#] Processing {pname} (ID: {cid})...")
        
        # 1. Sync Models
        t0 = time.monotonic()
        try:
            r_sync = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=15)
            sync_time = round((time.monotonic() - t0) * 1000, 1)
            sync_ok = r_sync.status_code == 200
            sync_json = r_sync.json() if sync_ok else {}
            models_synced = len(sync_json.get("models", [])) if isinstance(sync_json.get("models"), list) else 0
            print(f"    Sync Models: HTTP {r_sync.status_code} ({sync_time}ms) -> {models_synced} models")
        except Exception as e:
            sync_ok = False
            sync_time = round((time.monotonic() - t0) * 1000, 1)
            models_synced = 0
            print(f"    Sync Models: EXCEPTION ({e})")
            
        # 2. Test Connection
        t1 = time.monotonic()
        try:
            r_test = api.session.post(f"{api.api}/providers/{cid}/test", timeout=15)
            test_time = round((time.monotonic() - t1) * 1000, 1)
            test_json = r_test.json() if r_test.status_code == 200 else {}
            test_valid = test_json.get("valid", False)
            print(f"    Test Connection: HTTP {r_test.status_code} ({test_time}ms) -> valid={test_valid}")
        except Exception as e:
            test_valid = False
            test_time = round((time.monotonic() - t1) * 1000, 1)
            print(f"    Test Connection: EXCEPTION ({e})")
            
        results.append({
            "id": cid,
            "provider": pname,
            "sync_ok": sync_ok,
            "models_synced": models_synced,
            "test_valid": test_valid,
            "test_latency_ms": test_time
        })
        
    state_file = PROJECT_ROOT / "state" / "model_sync_health.json"
    state_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[+] Health & Sync report saved to {state_file}")
    
    valid_count = sum(1 for r in results if r.get("test_valid"))
    print(f"[+] Total Active & Healthy Connections: {valid_count}/{len(results)}")
    return True

if __name__ == "__main__":
    run_sync()
