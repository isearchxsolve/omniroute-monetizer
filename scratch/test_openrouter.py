#!/usr/bin/env python3
"""Test if openrouter works as an alternative backend."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, log, save_json

api = OmniRouteAPI()
api.login()

# Get openrouter connection
conns = api.get_connections()
openrouter_conn = None
for c in conns:
    if c.get('provider') == 'openrouter' and c.get('isActive'):
        openrouter_conn = c
        break

if not openrouter_conn:
    log("ERROR: openrouter not active", "err")
    sys.exit(1)

log(f"OpenRouter connection found: {openrouter_conn['id'][:8]}...", "ok")

# Try to find what models openrouter exposes
# Since /v1/models only has combos, try direct inference with common OpenRouter model names
test_models = [
    'openrouter/auto',
    'openrouter/gpt-4-free',
    'openrouter/claude-3.5-sonnet',
    'openrouter/claude-3-sonnet',
]

results = {}
for model in test_models:
    log(f"Testing {model}...", "info")
    result = api.chat_probe(model, timeout=30)
    status = result.get('http_status')
    ok = result.get('ok')
    results[model] = {'status': status, 'ok': ok, 'latency': result.get('latency')}
    log(f"  {model}: HTTP {status}, ok={ok}", "ok" if ok else "warn")

# If none work, try calling openrouter directly to see what error we get
if not any(r['ok'] for r in results.values()):
    log("\nAll model names failed. Trying generic 'openrouter' call...", "info")
    result = api.chat_probe('openrouter', timeout=30)
    results['generic-openrouter'] = result
    print(json.dumps(result, indent=2))

save_json('openrouter_test.json', results)
print(f"\n[+] OpenRouter test complete")
