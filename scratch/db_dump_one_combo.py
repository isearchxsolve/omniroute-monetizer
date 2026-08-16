import json, sqlite3

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
cur = con.cursor()
row = cur.execute("SELECT data FROM combos WHERE id=?", ("66e7fa63-0bd4-4d46-b06e-3669d407459c",)).fetchone()
data = json.loads(row[0])
print(json.dumps(data, indent=2))
con.close()
