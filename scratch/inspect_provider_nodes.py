#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path("C:/Users/Admin/.omniroute/storage.sqlite")
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()
cur.execute("PRAGMA table_info(provider_nodes)")
cols = cur.fetchall()
print("Columns in provider_nodes:")
for c in cols:
    print(f"  {c[1]} ({c[2]})")
