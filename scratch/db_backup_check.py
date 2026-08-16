import sqlite3, shutil, os, datetime

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect(db, timeout=30)
cur = con.cursor()
jm = cur.execute("PRAGMA journal_mode").fetchone()
print("journal_mode:", jm)
busy = cur.execute("PRAGMA busy_timeout").fetchone()
print("busy_timeout:", busy)
con.close()

# backup
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = db + f".bak_{ts}"
shutil.copy2(db, bak)
print("backup written:", bak, os.path.getsize(bak), "bytes")
# also copy wal/shm if present
for ext in ("-wal", "-shm"):
    p = db + ext
    if os.path.exists(p):
        shutil.copy2(p, bak + ext)
        print("copied", p)
