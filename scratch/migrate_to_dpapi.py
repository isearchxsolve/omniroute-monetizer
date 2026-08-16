#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))
from password_vault import store_password, retrieve_password
from oauth_keepalive import resolve_password

pw = resolve_password()
if pw:
    bin_path = store_password(pw)
    print(f"[+] Password successfully stored in DPAPI vault: {bin_path}")
    decrypted = retrieve_password(bin_path)
    assert decrypted == pw, "Verification failed!"
    print("[+] DPAPI retrieval verified 100% match.")
else:
    print("[-] No password found to migrate.")
