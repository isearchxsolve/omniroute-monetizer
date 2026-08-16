#!/usr/bin/env python3
"""
Extract Trae and Windsurf authentication tokens and inspect their structure.
T11 Redacted output.
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

def extract_vscdb(db_path: Path):
    if not db_path.exists():
        return {}
    data = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM ItemTable")
        for k, v in cursor.fetchall():
            data[k] = v
        conn.close()
    except Exception as e:
        data["_error"] = str(e)
    return data

def main():
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    
    print("=== TRAE EXTRACTION ===")
    trae_db = appdata / "TRAE SOLO" / "User" / "globalStorage" / "state.vscdb"
    if trae_db.exists():
        t_data = extract_vscdb(trae_db)
        print(f"Trae items count: {len(t_data)}")
        for k, v in t_data.items():
            if any(term in k.lower() for term in ["auth", "token", "account", "trae", "login", "user", "session"]):
                print(f"  Key: {k}")
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        print(f"    JSON keys: {list(parsed.keys())}")
                        for pk, pv in parsed.items():
                            print(f"      {pk}: {mask(pv)}")
                    else:
                        print(f"    Value: {mask(v)}")
                except Exception:
                    print(f"    Value: {mask(v)}")
                    
    print("\n=== WINDSURF EXTRACTION ===")
    windsurf_db = appdata / "Windsurf" / "User" / "globalStorage" / "state.vscdb"
    if windsurf_db.exists():
        w_data = extract_vscdb(windsurf_db)
        print(f"Windsurf items count: {len(w_data)}")
        for k, v in w_data.items():
            if any(term in k.lower() for term in ["auth", "token", "account", "codeium", "windsurf", "key", "login", "user", "session"]):
                print(f"  Key: {k}")
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        print(f"    JSON keys: {list(parsed.keys())}")
                        for pk, pv in parsed.items():
                            print(f"      {pk}: {mask(pv)}")
                    else:
                        print(f"    Value: {mask(v)}")
                except Exception:
                    print(f"    Value: {mask(v)}")

if __name__ == "__main__":
    main()
