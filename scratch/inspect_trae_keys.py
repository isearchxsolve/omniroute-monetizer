#!/usr/bin/env python3
"""
Inspect Trae and Windsurf keys specifically.
"""
import os
import sys
import json
import sqlite3
from pathlib import Path

def mask(val: str) -> str:
    if not val:
        return "<empty>"
    s = str(val)
    if len(s) <= 10:
        return "[REDACTED]"
    return f"{s[:6]}...{s[-4:]} (len={len(s)})"

appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))

print("=== TRAE KEYS ===")
trae_db = appdata / "TRAE SOLO" / "User" / "globalStorage" / "state.vscdb"
if trae_db.exists():
    conn = sqlite3.connect(f"file:{trae_db}?mode=ro", uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM ItemTable")
    for k, v in cursor.fetchall():
        if any(term in k.lower() for term in ["auth", "token", "trae", "user", "account", "login"]):
            print(f"Key: {k}")
            try:
                p = json.loads(v)
                print(f"  Type: {type(p).__name__}")
                if isinstance(p, dict):
                    for subk, subv in p.items():
                        print(f"    {subk}: {mask(subv)}")
                else:
                    print(f"    val: {mask(p)}")
            except Exception:
                print(f"    raw: {mask(v)}")
    conn.close()

print("\n=== WINDSURF AUTH STATUS ===")
windsurf_db = appdata / "Windsurf" / "User" / "globalStorage" / "state.vscdb"
if windsurf_db.exists():
    conn = sqlite3.connect(f"file:{windsurf_db}?mode=ro", uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM ItemTable WHERE key IN ('windsurfAuthStatus', 'codeium.windsurf-windsurf_auth', 'windsurf_auth-Kunal Das')")
    for k, v in cursor.fetchall():
        print(f"Key: {k}")
        try:
            p = json.loads(v)
            if isinstance(p, dict):
                for subk, subv in p.items():
                    print(f"  {subk}: {mask(subv)}")
            else:
                print(f"  val: {mask(p)}")
        except Exception:
            print(f"  raw: {mask(v)}")
    conn.close()
