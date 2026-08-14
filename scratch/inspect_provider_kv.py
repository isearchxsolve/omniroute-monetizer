import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

keys = [
    "cerebras:b533b28a-24d3-481f-ac5a-f0b9a562c55e",
    "alibaba:6116ca06-f7c9-4c91-82bc-43aade21e5cb",
    "cloudflare-ai:9b8e973a-75d8-4b5c-95b7-1241c24d0479",
    "cohere:4a1b2609-3d1f-41bc-8bd5-3e3e4baedaad",
    "lmarena:a0e46e4e-aaa2-4656-ae6a-a2146c9835fd",
    "zai-web:1504cdce-6851-4d99-975e-a3a89e338d80",
    "qoder:b2fe293d-41dc-4c70-83d6-0da0a834f279",
    "nvidia:574246f2-1cdf-48ad-83b6-2ca1b541f8e4"
]

print("=== PROVIDER METADATA IN KEY_VALUE ===")
for k in keys:
    c.execute("SELECT value FROM key_value WHERE key = ?", (k,))
    row = c.fetchone()
    if row:
        try:
            val = json.loads(row[0])
            print(f"\nKey: {k}")
            print(f"Data keys: {list(val.keys())}")
            if 'models' in val:
                print(f"Models ({len(val['models'])}): {val['models'][:5]}")
            if 'status' in val:
                print(f"Status: {val.get('status')}")
        except Exception as e:
            print(f"Key {k}: {row[0][:100]}")

conn.close()
