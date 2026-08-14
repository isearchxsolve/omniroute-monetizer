import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== SEARCHING ALL FREE MODELS ACROSS PROVIDERS ===")
cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels'")
synced_rows = cursor.fetchall()

free_models_by_provider = {}

for key, val_str in synced_rows:
    try:
        models = json.loads(val_str)
        provider_name = key.split(':')[0]
        
        for m in models:
            mid = m.get('id') if isinstance(m, dict) else str(m)
            mname = m.get('name') if isinstance(m, dict) else ""
            
            # Check for free criteria
            is_free = False
            if ':free' in mid.lower() or 'free' in mid.lower() or 'free' in mname.lower():
                is_free = True
            elif provider_name in ['qoder', 'nvidia', 'cloudflare-ai', 'github', 'antigravity', 'cerebras']:
                # Providers with full or standard free tiers
                is_free = True
                
            if is_free:
                free_models_by_provider.setdefault(provider_name, []).append((mid, mname))
    except Exception as e:
        pass

for prov, mlist in free_models_by_provider.items():
    print(f"\n[PROVIDER: {prov.upper()}] - {len(mlist)} free models")
    for mid, mname in mlist:
        print(f"  • {mid} ({mname})")

print("\n=== OPENROUTER EXPLICIT :free MODELS ===")
cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels' AND key LIKE 'openrouter%'")
or_row = cursor.fetchone()
if or_row:
    or_models = json.loads(or_row[1])
    or_free = [m for m in or_models if ':free' in (m.get('id') if isinstance(m, dict) else str(m))]
    print(f"OpenRouter :free models count: {len(or_free)}")
    for m in or_free:
        mid = m.get('id') if isinstance(m, dict) else str(m)
        mname = m.get('name') if isinstance(m, dict) else ""
        print(f"  • {mid} ({mname})")

