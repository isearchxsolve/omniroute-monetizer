import urllib.request
import json

req = urllib.request.Request('http://localhost:20128/api/providers', headers={'Authorization': 'Bearer sk-omniroute'})
try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        ainative_conns = [c for c in res.get('connections', []) if 'ainative' in c.get('provider', '').lower() or 'ainative' in c.get('name', '').lower()]
        for c in ainative_conns:
            print(f"Provider: {c.get('provider')}, Balance: {c.get('balance', 'Unknown')}, Limit: {c.get('limit', 'Unknown')}, Status: {c.get('status')}")
        if not ainative_conns:
            print('No AINative connections found.')
except Exception as e:
    print('Error:', e)
