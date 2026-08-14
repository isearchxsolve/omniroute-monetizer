import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== DETAILED PROVIDER STATUS & LAST ERRORS ===")
c.execute("""
    SELECT provider, name, auth_type, is_active, 
           length(api_key), length(access_token), 
           last_error, error_code, last_error_type
    FROM provider_connections 
    WHERE is_active = 1
""")

for row in c.fetchall():
    p, n, auth, active, key_len, tok_len, err, err_code, err_type = row
    print(f"[{p:<15}] Name: {str(n):<20} | Auth: {auth} | KeyLen: {key_len or 0} | TokLen: {tok_len or 0}")
    if err or err_code or err_type:
        print(f"   --> Last Error: [{err_code}] {err_type} - {str(err)[:100]}")

conn.close()
