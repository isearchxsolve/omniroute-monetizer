#!/usr/bin/env python3
"""Direct test of the nvidia/llama model through the OmniRoute inference API."""
import sys, json, time
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, log, save_json

api = OmniRouteAPI()

# Test 1: Try the model directly
model = 'nvidia/llama-3.1-nemotron-nano-vl-8b-v1'
log(f"Testing model directly: {model}", "info")
result = api.chat_probe(model, timeout=30)
print(json.dumps(result, indent=2))

# Test 2: Try through a combo alias
log(f"\nTesting through combo alias 'frontier'", "info")
result2 = api.chat_probe('frontier', timeout=30)
print(json.dumps(result2, indent=2))

# Test 3: Try another known working combo
log(f"\nTesting through combo alias 'auto/best-coding'", "info")
result3 = api.chat_probe('auto/best-coding', timeout=30)
print(json.dumps(result3, indent=2))

save_json('direct_model_test.json', {
    'test_model_direct': result,
    'test_frontier': result2,
    'test_auto_best_coding': result3,
})
