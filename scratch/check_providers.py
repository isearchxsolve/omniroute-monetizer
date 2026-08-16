#!/usr/bin/env python3
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()
api.login()
conns = api.get_connections()

result = {}
for c in conns:
    if c['provider'] in ['openrouter', 'nvidia', 'openai', 'anthropic']:
        result[c['provider']] = {
            'id': c.get('id'),
            'active': c.get('isActive'),
            'authType': c.get('authType'),
            'hasKey': bool(c.get('apiKey')),
            'error': c.get('error'),
        }

save_json('provider_status.json', result)
print(json.dumps(result, indent=2))
