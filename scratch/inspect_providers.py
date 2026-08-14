import sqlite3
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, name, enabled FROM provider_connections")
    rows = cursor.fetchall()
    print(f"\n--- provider_connections ({len(rows)}) ---")
    for r in rows:
        print(r)
except Exception as e:
    print(e)
