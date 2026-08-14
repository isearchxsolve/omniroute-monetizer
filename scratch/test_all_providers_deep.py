import sqlite3
import json
import requests
import time

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("""
    SELECT id, provider, name, auth_type, is_active, api_key, access_token, provider_specific_data
    FROM provider_connections
""")
rows = c.fetchall()
conn.close()

print(f"=== TESTING ALL {len(rows)} PROVIDERS IN DATABASE ===")

# Test each provider by asking OmniRoute for a model associated with that provider
# Or inspect what models each provider serves
# Let's inspect syncedAvailableModels from key_value table
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT key, value FROM key_value WHERE key LIKE 'syncedAvailableModels%' OR key LIKE 'provider_models%'")
cached_models = {}
for k, v in c.fetchall():
    try:
        cached_models[k] = json.loads(v)
    except:
        pass
conn.close()

print(f"Found {len(cached_models)} model cache entries in key_value.")
for k in list(cached_models.keys())[:10]:
    print(f"  Key: {k} -> {len(cached_models[k]) if isinstance(cached_models[k], list) else type(cached_models[k])}")

# Let's test each provider through OmniRoute's chat completions
# We will disable opencode-zen and opencode right away to stop the 401 errors
