import sqlite3

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT id, provider, auth_type, is_active FROM provider_connections WHERE provider IN ('lmarena', 'qoder', 'codex', 'amazon-q', 'cerebras', 'zai-web', 'antigravity')")
rows = c.fetchall()
for r in rows:
    print(r)

print("--- Lockouts ---")
c.execute("SELECT * FROM domain_lockout_state")
for r in c.fetchall():
    print(r)
    
print("--- Circuit Breakers ---")
c.execute("SELECT * FROM domain_circuit_breakers")
for r in c.fetchall():
    print(r)
