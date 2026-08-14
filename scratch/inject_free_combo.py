import sqlite3
import json
import uuid
import datetime

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"

# Create a new combo for auto/free-chat
combo_id = str(uuid.uuid4())
combo_name = "auto/free-chat"

combo_data = {
    "name": combo_name,
    "models": [
        {
            "id": str(uuid.uuid4()),
            "kind": "model",
            "model": "openrouter/auto",
            "providerId": "openrouter",
            "weight": 0
        },
        {
            "id": str(uuid.uuid4()),
            "kind": "model",
            "model": "github/gpt-4o-mini",
            "providerId": "github",
            "weight": 0
        }
    ],
    "strategy": "auto",
    "config": {
        "maxRetries": 3,
        "retryDelayMs": 500,
        "handoffThreshold": 0.85,
        "handoffModel": "",
        "maxMessagesForSummary": 30,
        "trackMetrics": True
    },
    "id": combo_id,
    "isHidden": False,
    "sortOrder": 10,
    "createdAt": datetime.datetime.utcnow().isoformat() + "Z",
    "updatedAt": datetime.datetime.utcnow().isoformat() + "Z",
    "version": 1,
    "description": "Directly injected via SQLite to fix free tier routing"
}

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if auto/free-chat already exists
    cursor.execute("SELECT id FROM combos WHERE name = ?", (combo_name,))
    existing = cursor.fetchone()
    
    if existing:
        print(f"Updating existing combo: {existing[0]}")
        cursor.execute("UPDATE combos SET data = ?, updated_at = ? WHERE id = ?", 
                       (json.dumps(combo_data), combo_data["updatedAt"], existing[0]))
    else:
        print(f"Inserting new combo: {combo_id}")
        cursor.execute("INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (combo_id, combo_name, json.dumps(combo_data), 10, combo_data["createdAt"], combo_data["updatedAt"]))
        
    conn.commit()
    conn.close()
    print("Database updated successfully!")
except Exception as e:
    print(f"Error: {e}")
