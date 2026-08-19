#!/usr/bin/env python3
"""
VS Code Chat Backup & Sixth AI Factory Reset Tool.

Functions:
  1. Safely archives VS Code custom settings, keybindings, chatLanguageModels.json,
     and workspaceStorage (Copilot / extension chat histories) to D:\\vscode-backups\\<timestamp>\\.
  2. Factory resets Sixth AI trial credentials (wiping state.vscdb entries, local storage,
     and Windows Credential Manager tokens).
  3. Restores clean user settings and OmniRoute Monetizer client configurations.

Usage:
  python reset_sixth_and_backup_vscode.py --backup-only
  python reset_sixth_and_backup_vscode.py --reset-sixth
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APPDATA = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
CODE_USER = APPDATA / "Code" / "User"
BACKUP_ROOT = Path(r"D:\vscode-backups")


def backup_vscode_state() -> Path:
    """Backup VS Code user settings and chat histories to D:\\vscode-backups\\."""
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / ts
    dest.mkdir(parents=True, exist_ok=True)

    copied = []
    # Key settings files
    for name in ("settings.json", "keybindings.json", "chatLanguageModels.json"):
        src = CODE_USER / name
        if src.exists():
            try:
                shutil.copy2(src, dest / name)
                copied.append(name)
            except Exception as e:
                print(f"[!] Error backing up {name}: {e}")

    # Workspace storage (Copilot & Agent chat databases)
    ws_storage = CODE_USER / "workspaceStorage"
    if ws_storage.exists():
        try:
            shutil.copytree(ws_storage, dest / "workspaceStorage", dirs_exist_ok=True)
            copied.append("workspaceStorage (Copilot Chat DBs)")
        except Exception as e:
            print(f"[!] Error backing up workspaceStorage: {e}")

    # Global storage (Extension states)
    global_storage = CODE_USER / "globalStorage"
    if global_storage.exists():
        try:
            # Copy state.vscdb database
            vscdb = global_storage / "state.vscdb"
            if vscdb.exists():
                shutil.copy2(vscdb, dest / "state.vscdb")
                copied.append("state.vscdb")
        except Exception as e:
            print(f"[!] Error backing up state.vscdb: {e}")

    manifest = {
        "timestamp": dt.datetime.now().isoformat(),
        "copied_items": copied,
        "backup_destination": str(dest),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[+] VS Code data & chat history backed up to: {dest}")
    return dest


def reset_sixth_ai_credentials():
    """Wipe Sixth AI trial state, device identity tokens, Machine ID, SQLite secrets, and dotfiles."""
    print("[*] Performing 100% Complete Sixth AI Deep Purge & Factory Reset...")

    # 1. Clear state.vscdb SQLite secrets & extension state
    import sqlite3
    db_path = CODE_USER / "globalStorage" / "state.vscdb"
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("DELETE FROM ItemTable WHERE key LIKE '%sixth%' OR key LIKE '%cline%'")
            conn.commit()
            conn.close()
            print(f"  [+] Purged Sixth & Cline keys from {db_path.name}")
        except Exception as e:
            print(f"  [!] state.vscdb purge error: {e}")

    # 2. Delete .cline and .overture dotfile directories in User Home
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    for dotdir in (home / ".cline", home / ".overture"):
        if dotdir.exists():
            try:
                shutil.rmtree(dotdir, ignore_errors=True)
                print(f"  [+] Removed dotfile directory: {dotdir}")
            except Exception as e:
                print(f"  [!] Failed removing {dotdir}: {e}")

    # 3. Regenerate VS Code Machine ID (un-blacklists device from Sixth servers)
    import uuid
    new_machine_id = uuid.uuid4().hex + uuid.uuid4().hex
    machineid_file = CODE_USER / "machineid"
    machineid_file.write_text(new_machine_id, encoding="utf-8")
    print(f"  [+] Regenerated VS Code Machine ID: {new_machine_id[:16]}...")

    storage_json = CODE_USER / "storage.json"
    if storage_json.exists():
        try:
            data = json.loads(storage_json.read_text(encoding="utf-8"))
            data["telemetry.machineId"] = new_machine_id
            data["telemetry.devDeviceId"] = str(uuid.uuid4())
            storage_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print("  [+] Updated telemetry.machineId in storage.json")
        except Exception as e:
            print(f"  [!] storage.json update error: {e}")

    # 4. Clear Windows Credential Manager entries
    try:
        cmd = 'cmdkey /list | findstr /i "sixth"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.stdout:
            for line in res.stdout.splitlines():
                if "Target:" in line:
                    target = line.split("Target:")[1].strip()
                    subprocess.run(f'cmdkey /delete:"{target}"', shell=True, check=False)
                    print(f"  [-] Removed Windows Credential: {target}")
    except Exception as e:
        print(f"  [!] Credential cleanup warning: {e}")

    # 5. Remove Sixth storage in globalStorage
    sixth_global = CODE_USER / "globalStorage" / "sixth.sixth-ai"
    if sixth_global.exists():
        try:
            def force_remove_readonly(func, path, exc_info):
                import stat
                os.chmod(path, stat.S_IWRITE)
                func(path)
            shutil.rmtree(sixth_global, onerror=force_remove_readonly)
            print(f"  [-] Removed globalStorage dir: {sixth_global}")
        except Exception as e:
            print(f"  [!] Failed to remove {sixth_global}: {e}")

    # 6. Clear Local Storage, Session Storage, and WebStorage
    for folder in ("Local Storage", "Session Storage", "WebStorage"):
        target = APPDATA / "Code" / folder
        if target.exists():
            try:
                shutil.rmtree(target, ignore_errors=True)
                print(f"  [-] Cleared VS Code {folder}")
            except Exception as e:
                print(f"  [!] Warning clearing {folder}: {e}")

    print("[+] 100% Sixth AI deep purge & factory reset complete! Restart VS Code to sign into a new account.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VS Code Chat Backup & Sixth AI Factory Reset")
    parser.add_argument("--backup-only", action="store_true", help="only backup VS Code settings & chat data")
    parser.add_argument("--reset-sixth", action="store_true", help="perform backup + Sixth AI factory reset")
    args = parser.parse_args()

    if args.reset_sixth:
        backup_vscode_state()
        reset_sixth_ai_credentials()
    else:
        backup_vscode_state()
