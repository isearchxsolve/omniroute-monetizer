#!/usr/bin/env python3
"""
Inspect all local installed AI coding runtimes, Electron apps, CLI configs,
and Chrome cookie stores to find live authentication tokens without human intervention.

Redacts all secrets before outputting (T11 compliant).
"""
import os
import sys
import json
import sqlite3
import re
from pathlib import Path

def mask(val: str) -> str:
    if not val:
        return "<empty>"
    s = str(val)
    if len(s) <= 10:
        return "[REDACTED]"
    return f"{s[:6]}...{s[-4:]} (len={len(s)})"

def inspect_json_file(path: Path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data
    except Exception as e:
        return f"Error: {e}"

def search_sqlite_keys(db_path: Path, patterns: list):
    if not db_path.exists():
        return {}
    results = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            try:
                cursor.execute(f"SELECT * FROM {table} LIMIT 500;")
                rows = cursor.fetchall()
                for row in rows:
                    row_str = str(row)
                    for pat in patterns:
                        if re.search(pat, row_str, re.I):
                            results[f"{table}:{pat}"] = row_str[:200]
            except Exception:
                pass
        conn.close()
    except Exception as e:
        results["error"] = str(e)
    return results

def main():
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    localappdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    
    print("=== 1. CLAUDE RUNTIMES ===")
    claude_json = home / ".claude.json"
    if claude_json.exists():
        data = inspect_json_file(claude_json)
        print(f"~/.claude.json found: keys = {list(data.keys()) if isinstance(data, dict) else data}")
        if isinstance(data, dict):
            for k, v in data.items():
                if any(sec in k.lower() for sec in ["token", "key", "auth", "session", "user", "email"]):
                    print(f"  {k}: {mask(v)}")
    else:
        print("~/.claude.json not found")
        
    claude_appdata = appdata / "Claude"
    print(f"AppData/Claude exists: {claude_appdata.exists()}")
    if claude_appdata.exists():
        for p in claude_appdata.rglob("*.json"):
            print(f"  Found Claude json: {p.relative_to(claude_appdata)}")

    print("\n=== 2. TRAE RUNTIMES ===")
    trae_solo = appdata / "TRAE SOLO"
    print(f"AppData/TRAE SOLO exists: {trae_solo.exists()}")
    if trae_solo.exists():
        for db in trae_solo.rglob("state.vscdb"):
            print(f"  Found Trae vscdb: {db}")
            hits = search_sqlite_keys(db, [r"token", r"auth", r"trae", r"account", r"jwt", r"session"])
            for k, v in hits.items():
                print(f"    hit {k}: {mask(v)}")
                
    print("\n=== 3. WINDSURF RUNTIMES ===")
    windsurf_appdata = appdata / "Windsurf"
    windsurf_home = home / ".windsurf"
    print(f"AppData/Windsurf exists: {windsurf_appdata.exists()}, ~/.windsurf exists: {windsurf_home.exists()}")
    if windsurf_appdata.exists():
        for db in windsurf_appdata.rglob("state.vscdb"):
            print(f"  Found Windsurf vscdb: {db}")
            hits = search_sqlite_keys(db, [r"codeium", r"token", r"auth", r"windsurf", r"apiKey", r"session"])
            for k, v in hits.items():
                print(f"    hit {k}: {mask(v)}")

    print("\n=== 4. NIM / AGENT RUNTIMES ===")
    nim_conf = home / ".nim_agent_config.json"
    nim_sess = home / ".nim_agent_sessions.json"
    if nim_conf.exists():
        print(f"~/.nim_agent_config.json found: keys = {list(inspect_json_file(nim_conf).keys())}")
    if nim_sess.exists():
        print(f"~/.nim_agent_sessions.json found: keys = {list(inspect_json_file(nim_sess).keys())}")

    print("\n=== 5. CHROME PROFILE SESSIONS ===")
    profile_dir = Path("D:/omniroute-chrome-profile")
    storage_state = Path("state/browser_profile/storage_state.json")
    if storage_state.exists():
        sdata = inspect_json_file(storage_state)
        if isinstance(sdata, dict):
            cookies = sdata.get("cookies", [])
            domains = set(c.get("domain", "") for c in cookies)
            print(f"storage_state.json domains ({len(cookies)} cookies): {sorted(domains)}")
            for c in cookies:
                dom = c.get("domain", "")
                if any(x in dom for x in ["claude", "anthropic", "trae", "codeium", "github", "openrouter", "google"]):
                    print(f"  {dom} -> {c.get('name')}: expires={c.get('expires')}")

if __name__ == "__main__":
    main()
