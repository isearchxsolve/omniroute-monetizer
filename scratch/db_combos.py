import sqlite3, json

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
cur = con.cursor()

cols = [c[1] for c in cur.execute("PRAGMA table_info(combos)")]
print("combos cols:", cols)

rows = cur.execute("SELECT * FROM combos").fetchall()
print(f"\n{len(rows)} combos")
for r in rows:
    d = dict(zip(cols, r))
    name = d.get("name") or d.get("id")
    models = d.get("models") or d.get("models_json") or d.get("model_list")
    print(f"\n=== {name} (id={str(d.get('id'))[:8]}) ===")
    for k, v in d.items():
        if v is None:
            continue
        vs = str(v)
        if len(vs) > 400:
            vs = vs[:400] + "..."
        print(f"  {k}: {vs}")
con.close()
