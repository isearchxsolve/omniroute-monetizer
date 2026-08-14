import requests

BASE_URL = 'http://localhost:20128'

try:
    print("Testing without ANY auth header...")
    resp = requests.get(f"{BASE_URL}/api/combos", timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"Combos: {len(resp.json().get('data', []))}")
except Exception as e:
    print(f"Error: {e}")
