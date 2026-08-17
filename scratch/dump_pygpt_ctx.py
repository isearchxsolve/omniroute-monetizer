"""Dump ctx_item rows to see inputs/outputs of failed agent runs."""
import sqlite3

DB = r"C:\Users\Admin\.config\pygpt-net\db.sqlite"

c = sqlite3.connect(DB)
cur = c.cursor()

cur.execute("""
SELECT id, meta_id, mode, model, input_name, output_name,
       substr(input,1,200), substr(output,1,500), input_ts, output_ts, is_internal
FROM ctx_item ORDER BY id
""")
for r in cur.fetchall():
    print("=" * 80)
    print(f"id={r[0]} meta={r[1]} mode={r[2]} model={r[3]}")
    print(f"input_name={r[4]} output_name={r[5]} internal={r[10]}")
    print(f"input_ts={r[8]} output_ts={r[9]}")
    print(f"INPUT : {r[6]!r}")
    print(f"OUTPUT: {r[7]!r}")

print("\n=== ctx_meta ===")
cur.execute("SELECT id, uuid, mode, model, last_mode, last_model, preset_id, status, name FROM ctx_meta")
for r in cur.fetchall():
    print(r)

c.close()
