#!/usr/bin/env python3
import requests
import json
import sqlite3
import os
from pathlib import Path

appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
windsurf_db = appdata / "Windsurf" / "User" / "globalStorage" / "state.vscdb"
conn = sqlite3.connect(f"file:{windsurf_db}?mode=ro", uri=True)
cursor = conn.cursor()
cursor.execute("SELECT value FROM ItemTable WHERE key='windsurfAuthStatus'")
api_key = json.loads(cursor.fetchone()[0]).get("apiKey", "")
conn.close()

endpoints = [
    "https://api.codeium.com/api/v1/GetStatus",
    "https://server.codeium.com/api/v1/GetStatus",
    "https://api.codeium.com/api/v1/GetCommandModelConfigs",
    "https://server.codeium.com/api/v1/GetCommandModelConfigs"
]

for url in endpoints:
    try:
        r = requests.post(url, json={"metadata": {"api_key": api_key, "ide_name": "windsurf"}}, timeout=5)
        print(f"{url} -> HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"{url} -> {e}")
