#!/usr/bin/env python3
"""Test what models are actually available from active providers."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json, log

api = OmniRouteAPI()
api.login()

conns = api.get_connections()
active = [c for c in conns if c.get('isActive')]
log(f"Testing {len(active)} active connections", "info")

results = {}
for conn in active[:10]:  # Test first 10 active providers
    prov = conn.get('provider')
    cid = conn.get('id')
    log(f"Testing {prov}...", "info")
    
    # Try refresh to populate metadata
    refresh_res = api.refresh_connection(cid)
    test_res = api.test_connection(cid)
    
    results[prov] = {
        'id': cid,
        'refresh_status': refresh_res.get('http_status'),
        'test_status': test_res.get('http_status'),
        'test_valid': test_res.get('result', {}).get('valid'),
        'test_info': str(test_res.get('result', {}))[:300],
    }
    log(f"  {prov}: refresh={refresh_res.get('http_status')}, test={test_res.get('http_status')}", "ok")

save_json('provider_test_results.json', results)
print(json.dumps(results, indent=2))
