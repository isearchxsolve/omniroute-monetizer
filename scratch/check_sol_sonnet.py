import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== CHECKING GPT-SOL & SONNET 5 ACROSS ALL PROVIDERS & TABLES ===")

# 1. Check syncedAvailableModels
cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels'")
rows = cursor.fetchall()
for k, v in rows:
    try:
        models = json.loads(v)
        for m in models:
            mid = m.get('id') if isinstance(m, dict) else str(m)
            mname = m.get('name') if isinstance(m, dict) else ""
            if any(term in mid.lower() or term in mname.lower() for term in ['sol', 'sonnet-5', 'sonnet 5', 'gpt-5.6']):
                print(f"[syncedAvailableModels] Provider: {k} -> ID: {mid} | Name: {mname}")
    except Exception as e:
        pass

# 2. Check modelAliases
cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'modelAliases'")
aliases = cursor.fetchall()
for k, v in aliases:
    if any(term in k.lower() or term in v.lower() for term in ['sol', 'sonnet-5', 'sonnet 5', 'gpt-5.6']):
        print(f"[modelAliases] {k} -> {v}")

# 3. Check model_intelligence
cursor.execute("SELECT model, category, score, elo_raw FROM model_intelligence WHERE model LIKE '%sol%' OR model LIKE '%sonnet-5%' OR model LIKE '%gpt-5.6%'")
for r in cursor.fetchall():
    print(f"[model_intelligence] Model: {r[0]} | Cat: {r[1]} | Score: {r[2]} | ELO: {r[3]}")

# 4. Check combos
cursor.execute("SELECT id, name, data FROM combos")
for r in cursor.fetchall():
    cdata = json.loads(r[2])
    for m in cdata.get('models', []):
        mid = m.get('model', '')
        if any(term in mid.lower() for term in ['sol', 'sonnet-5', 'sonnet 5', 'gpt-5.6']):
            print(f"[combos] Combo: {r[1]} -> Model: {mid} (Provider: {m.get('providerId')})")

# 5. Check active provider connections matching the providers
print("\n=== ACTIVE PROVIDER CONNECTIONS FOR THESE PROVIDERS ===")
cursor.execute("SELECT id, provider, name, auth_type, is_active FROM provider_connections WHERE is_active = 1")
for p in cursor.fetchall():
    print(f"Provider: {p[1]} (ID: {p[0]}, Name: {p[2]}, Auth: {p[3]})")
