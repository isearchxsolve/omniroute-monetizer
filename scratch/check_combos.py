import requests, json, base64

BASE_URL = 'http://localhost:20128'
auth_str = base64.b64encode(b":<REDACTED>").decode()
headers = {
    "Authorization": f"Basic {auth_str}",
    "Content-Type": "application/json"
}

try:
    resp = requests.get(f"{BASE_URL}/api/combos", headers=headers, timeout=10)
    print(f"Combos Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2)[:500])
except Exception as e:
    print(f"Error fetching combos: {e}")

try:
    resp = requests.get(f"{BASE_URL}/api/providers", headers=headers, timeout=10)
    print(f"\nProviders Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2)[:1000])
except Exception as e:
    print(f"Error fetching providers: {e}")
