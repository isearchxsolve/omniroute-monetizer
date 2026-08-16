#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect(r'C:\Users\Admin\.omniroute\storage.sqlite')
c = conn.cursor()
c.execute("DELETE FROM provider_connections WHERE created_at > '2026-08-16T07:50:00.000Z'")
conn.commit()

remaining = c.execute("SELECT COUNT(*) FROM provider_connections").fetchone()[0]
print(f"[+] Restored exact original provider connections count: {remaining}")
