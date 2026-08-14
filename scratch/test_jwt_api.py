import sqlite3
import json
import jwt
import time
import requests

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT value FROM key_value WHERE key = 'jwtSecret'")
row = c.fetchone()
jwt_secret = json.loads(row[0])
conn.close()

print(f"Loaded jwtSecret: {jwt_secret[:10]}...")

# Generate admin token
payload = {
    "sub": "admin",
    "role": "admin",
    "iat": int(time.time()),
    "exp": int(time.time()) + 3600 * 24 * 365
}

token = jwt.encode(payload, jwt_secret, algorithm="HS256")
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

resp = requests.get("http://localhost:20128/api/combos", headers=headers, timeout=5)
print(f"GET /api/combos: HTTP {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"Combos returned from live API: {len(data)}")
    for item in data:
        print(f"  Combo: {item.get('name')} | ID: {item.get('id')}")
else:
    print(f"Error: {resp.text}")

resp_mappings = requests.get("http://localhost:20128/api/model-mappings", headers=headers, timeout=5)
print(f"\nGET /api/model-mappings: HTTP {resp_mappings.status_code}")
if resp_mappings.status_code == 200:
    data = resp_mappings.json()
    print(f"Mappings returned from live API: {len(data)}")
    for item in data:
        print(f"  Mapping: {item.get('pattern')} -> {item.get('combo_id')}")
else:
    print(f"Error: {resp_mappings.text}")
