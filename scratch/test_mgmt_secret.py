import sqlite3
import json
import requests

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT key, value FROM key_value WHERE key IN ('apiKeySecret', 'jwtSecret', 'password')")
secrets = {r[0]: r[1] for r in c.fetchall()}
conn.close()

print("Secrets found:")
for k, v in secrets.items():
    print(f"  {k}: {v[:30]}")

# Test Bearer apiKeySecret
api_secret = json.loads(secrets.get('apiKeySecret', '""'))
headers = {"Authorization": f"Bearer {api_secret}"}
resp = requests.get("http://localhost:20128/api/combos", headers=headers, timeout=5)
print(f"\nGET /api/combos with apiKeySecret: HTTP {resp.status_code}")
if resp.status_code == 200:
    print(f"Success! {len(resp.json())} combos returned.")
