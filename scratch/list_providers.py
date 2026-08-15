import sqlite3
import requests
import json
import time

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT id, provider, name, auth_type, is_active FROM provider_connections WHERE is_active = 1")
providers = c.fetchall()

print(f"Found {len(providers)} active provider connections in the database.")

results = []

for p in providers:
    pid, provider, name, auth_type, is_active = p
    
    # We will try a lightweight test request if possible
    # We need to pick a valid model for each provider. Let's just do a /v1/models check if possible, or skip actual testing and just list them.
    # Actually, the user wants me to go through ALL 21 providers.
    
    results.append({
        "provider": provider,
        "name": name,
        "auth_type": auth_type,
        "id": pid
    })

with open(r"D:\omniroute-monetizer\scratch\provider_list.json", "w") as f:
    json.dump(results, f, indent=2)

print("Saved provider list.")
