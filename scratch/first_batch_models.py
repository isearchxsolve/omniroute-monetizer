import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

first_batch_providers = [
    'nvidia', 'opencode', 'openrouter', 'antigravity', 'amazon-q', 'clinepass', 
    'github', 'grok-cli', 'kilocode', 'alibaba', 'kimi-coding', 'zai-web', 
    'lmarena', 'opencode-zen', 'kiro'
]

cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels'")
synced_rows = dict(cursor.fetchall())

print("FIRST BATCH ACTIVE PROVIDERS:")
for p in first_batch_providers:
    # search key in synced_rows
    matched = None
    for k, v in synced_rows.items():
        if k.startswith(f"{p}:") or k == p:
            matched = (k, json.loads(v))
            break
    if matched:
        print(f"\n[{p.upper()}] ({len(matched[1])} models) - Key: {matched[0]}")
        for m in matched[1]:
            mid = m.get('id') if isinstance(m, dict) else str(m)
            mname = m.get('name') if isinstance(m, dict) else ""
            print(f"  • {mid} ({mname})")
    else:
        print(f"\n[{p.upper()}] - No custom synced models (uses standard default models)")
