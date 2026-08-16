#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path("C:/Users/Admin/.omniroute/storage.sqlite")
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()
cur.execute("PRAGMA table_info(provider_connections)")
cols = cur.fetchall()
print("Columns in provider_connections:")
for c in cols:
    print(f"  {c[1]} ({c[2]})")

cur.execute("SELECT id, provider, auth_type, is_active, provider_specific_data FROM provider_connections LIMIT 10")
for r in cur.fetchall():
    print("Row:", r)
