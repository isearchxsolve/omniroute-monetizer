import sqlite3
import requests
import json
import time

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Let's inspect the models for windsurf, antigravity, clinepass, kiro, trae, amazon-q, codex
oauth_providers = [
    "windsurf",
    "antigravity",
    "agy",
    "clinepass",
    "cline",
    "kiro",
    "trae",
    "amazon-q",
    "codex",
    "ainative",
    "lmarena"
]

print("=== INSPECTING OAUTH / ADVANCED PROVIDER MODELS ===")
for p in oauth_providers:
    c.execute("SELECT id, name, is_active, auth_type, length(access_token), length(refresh_token), provider_specific_data FROM provider_connections WHERE provider = ?", (p,))
    rows = c.fetchall()
    for row in rows:
        pid, name, active, auth, tok_len, ref_len, spec = row
        print(f"\nProvider: {p:<12} | ID: {pid[:8]} | Name: {name} | Active: {active} | TokLen: {tok_len}")
        
        # Check key_value for this provider's model list
        c.execute("SELECT value FROM key_value WHERE key = ? OR key = ?", (f"{p}:{pid}", pid))
        kv = c.fetchone()
        if kv:
            try:
                models = json.loads(kv[0])
                if isinstance(models, list):
                    print(f"   Available models ({len(models)}): {[m.get('id') if isinstance(m, dict) else m for m in models[:10]]}")
            except Exception as e:
                print(f"   Error parsing models: {e}")

conn.close()
