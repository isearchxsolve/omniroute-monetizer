#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path("C:/Users/Admin/.omniroute/storage.sqlite")
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cur.fetchall()]
for t in sorted(tables):
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    if "conn" in t or "prov" in t or "node" in t or "model" in t or "key" in t:
        print(f"Table: {t:30} Count: {cnt}")
