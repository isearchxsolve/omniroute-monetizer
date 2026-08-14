import sqlite3
import uuid
import datetime

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Map aliases to their combo IDs
mappings = [
    ("frontier", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 10000, "Frontier Free Cascade -> Frontier Max combo"),
    ("auto/pro-coding", "66e7fa63-0bd4-4d46-b06e-3669d407459c", 10000, "Pro Coding Free Cascade"),
    ("auto/pro-reasoning", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 10000, "Pro Reasoning Free Cascade"),
    ("auto/free-chat", "7e521395-b148-4755-903a-4d3152d44019", 10000, "Free Chat Zero Cost Cascade"),
    ("auto/free-frontier", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 10000, "Free Frontier Cascade")
]

now = datetime.datetime.utcnow().isoformat() + "Z"

for pattern, combo_id, priority, desc in mappings:
    cursor.execute("SELECT id FROM model_combo_mappings WHERE pattern = ?", (pattern,))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE model_combo_mappings SET combo_id = ?, enabled = 1, priority = ?, description = ?, updated_at = ? WHERE pattern = ?",
                       (combo_id, priority, desc, now, pattern))
        print(f"Updated mapping for: {pattern}")
    else:
        cursor.execute("INSERT INTO model_combo_mappings (id, pattern, combo_id, priority, enabled, description, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                       (str(uuid.uuid4()), pattern, combo_id, priority, desc, now, now))
        print(f"Inserted mapping for: {pattern}")

conn.commit()
conn.close()
print("All Model Combo Mappings configured and enabled in OmniRoute!")
