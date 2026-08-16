import json, sqlite3

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
cur = con.cursor()

print("=== combos table schema ===")
for row in cur.execute("PRAGMA table_info(combos)"):
    print(row)

print("\n=== all combos rows ===")
cols = [c[1] for c in cur.execute("PRAGMA table_info(combos)")]
print("columns:", cols)
for row in cur.execute("SELECT * FROM combos"):
    d = dict(zip(cols, row))
    data = d.get("data")
    try:
        parsed = json.loads(data) if data else {}
    except Exception:
        parsed = {"_parse_error": True}
    print(f"\nid={d.get('id')}")
    for k, v in d.items():
        if k == "data":
            continue
        print(f"  {k}={v!r}")
    print(f"  data.name={parsed.get('name')!r} data.models_count={len(parsed.get('models') or [])} data.version={parsed.get('version')}")
    if parsed.get("name") in ("auto/pro-coding", "Frontier Max", "auto/free-chat", "auto/asian-flagships"):
        print("  FULL DATA:", json.dumps(parsed, indent=2)[:1500])
con.close()
