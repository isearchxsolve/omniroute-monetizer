#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect(r'C:\Users\Admin\.omniroute\storage.sqlite')
c = conn.cursor()

# Set only verified providers to active
c.execute("UPDATE provider_connections SET is_active=0 WHERE test_status != 'active'")
conn.commit()

active_count = c.execute("SELECT COUNT(*) FROM provider_connections WHERE is_active=1").fetchone()[0]
total_count = c.execute("SELECT COUNT(*) FROM provider_connections").fetchone()[0]
print(f"[+] Total providers in DB: {total_count}, Active verified providers: {active_count}")
