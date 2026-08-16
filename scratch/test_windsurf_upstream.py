#!/usr/bin/env python3
"""
Test Windsurf API key against Codeium/Windsurf upstream API.
"""
import os
import sys
import json
import sqlite3
import requests
from pathlib import Path

def mask(val: str) -> str:
    if not val:
        return "<empty>"
    s = str(val)
    if len(s) <= 10:
        return "[REDACTED]"
    return f"{s[:6]}...{s[-4:]} (len={len(s)})"

appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
windsurf_db = appdata / "Windsurf" / "User" / "globalStorage" / "state.vscdb"

api_key = ""
if windsurf_db.exists():
    conn = sqlite3.connect(f"file:{windsurf_db}?mode=ro", uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM ItemTable WHERE key='windsurfAuthStatus'")
    row = cursor.fetchone()
    if row:
        p = json.loads(row[0])
        api_key = p.get("apiKey", "")
    conn.close()

print(f"Extracted Windsurf apiKey: {mask(api_key)}")

if not api_key:
    print("No apiKey found")
    sys.exit(1)

# Codeium / Windsurf API endpoint
url = "https://api.codeium.com/register_user/"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Test chat or user status
# Let's test with https://api.codeium.com
print("Testing against Codeium/Windsurf API...")
try:
    r = requests.post(
        "https://api.codeium.com/api/v1/GetProcesses",
        headers=headers,
        json={"metadata": {"api_key": api_key}},
        timeout=10
    )
    print(f"GetProcesses HTTP {r.status_code}: {r.text[:200]}")
except Exception as e:
    print(f"Request error: {e}")
