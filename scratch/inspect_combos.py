import requests
import json
import uuid

BASE_URL = "http://localhost:20128"
s = requests.Session()
login_res = s.post(f"{BASE_URL}/api/auth/login", json={"password": "Keross@321"})
print("Login status:", login_res.status_code)

combos_res = s.get(f"{BASE_URL}/api/combos")
combos_data = combos_res.json()
print("Combos data:", json.dumps(combos_data, indent=2))
