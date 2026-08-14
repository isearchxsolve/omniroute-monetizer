import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get provider IDs
cursor.execute("SELECT id, provider, name, is_active FROM provider_connections WHERE is_active = 1")
providers = {p[1]: p[0] for p in cursor.fetchall()}
print("Active Provider IDs:", providers)

# Check how models are stored in syncedAvailableModels
for p in ['qoder', 'opencode-zen', 'opencode', 'lmarena', 'nvidia', 'github']:
    cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels' AND key LIKE ?", (f"{p}%",))
    row = cursor.fetchone()
    if row:
        models = json.loads(row[1])
        print(f"\nProvider: {p} ({len(models)} models)")
        for m in models:
            mid = m.get('id') if isinstance(m, dict) else str(m)
            if any(term in mid.lower() for term in ['sol', 'sonnet-5', 'k3', 'qwen3.8', 'glm-5.2', 'deepseek-v4', 'nemotron-3-ultra']):
                print(f"   • {mid} (Name: {m.get('name') if isinstance(m, dict) else ''})")
