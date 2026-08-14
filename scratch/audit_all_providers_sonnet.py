import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== COMPLETE AUDIT OF ALL PROVIDER CONNECTIONS ===")
c.execute("""
    SELECT id, provider, name, email, auth_type, is_active, 
           length(api_key), length(access_token), length(refresh_token),
           default_model, provider_specific_data, last_error
    FROM provider_connections
""")
rows = c.fetchall()

for row in rows:
    pid, provider, name, email, auth_type, is_active, key_len, tok_len, ref_len, def_model, spec_data, last_err = row
    print(f"[{provider:<15}] ID: {pid[:8]} | Name: {str(name):<20} | Active: {is_active} | Auth: {auth_type} | Key: {key_len or 0} | Tok: {tok_len or 0} | Ref: {ref_len or 0} | DefModel: {def_model}")
    if spec_data:
        try:
            d = json.loads(spec_data)
            print(f"   SpecData keys: {list(d.keys())}")
        except:
            print(f"   SpecData: {spec_data[:60]}")

print("\n=== SEARCHING FOR SONNET IN ALL KEY_VALUE ENTRIES ===")
c.execute("SELECT key, value FROM key_value WHERE value LIKE '%sonnet%'")
kv_matches = c.fetchall()
print(f"Found {len(kv_matches)} keys containing 'sonnet':")
for k, v in kv_matches:
    print(f"  Key: {k}")
    try:
        data = json.loads(v)
        if isinstance(data, list):
            matching_models = [m for m in data if isinstance(m, dict) and 'sonnet' in m.get('id', '').lower()]
            print(f"    Matching models in list: {[m.get('id') for m in matching_models]}")
    except:
        pass

conn.close()
