#!/usr/bin/env python3
"""
Inspect OmniRoute database tables and schema.
"""
import sqlite3
import os
from pathlib import Path

data_dirs = [
    Path.home() / ".omniroute",
    Path("C:/Users/Admin/.omniroute"),
    Path(os.environ.get("DATA_DIR", "")),
    Path(os.environ.get("APPDATA", "")) / "omniroute",
    Path(os.environ.get("LOCALAPPDATA", "")) / "omniroute"
]

db_path = None
for d in data_dirs:
    p = d / "storage.sqlite"
    if p.exists():
        db_path = p
        break

print(f"DB Path: {db_path}")
if db_path:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    print(f"Tables ({len(tables)}): {tables}")
    
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [f"{c[1]} ({c[2]})" for c in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"\n--- {t} (rows: {cnt}) ---")
        print(f"  Columns: {', '.join(cols)}")
        if cnt > 0 and cnt <= 5:
            cur.execute(f"SELECT * FROM {t} LIMIT 5")
            for r in cur.fetchall():
                print(f"  Row: {r}")
