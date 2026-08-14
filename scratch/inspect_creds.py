import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, provider, name, auth_type, api_key, access_token, is_active FROM provider_connections")
rows = cursor.fetchall()

print("=== PROVIDER CREDENTIALS & STATUS ===")
for r in rows:
    has_api_key = bool(r[4])
    api_key_len = len(r[4]) if r[4] else 0
    has_token = bool(r[5])
    token_len = len(r[5]) if r[5] else 0
    print(f"ID: {r[0]} | Provider: {r[1]:<15} | Name: {str(r[2]):<20} | Auth: {r[3]:<8} | Has Key: {has_api_key} ({api_key_len}) | Has Token: {has_token} ({token_len}) | Active: {r[6]}")

