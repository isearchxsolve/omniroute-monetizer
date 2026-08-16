#!/usr/bin/env python3
"""One-time vault migration: re-encrypt the management password with
machine-scoped DPAPI (CRYPTPROTECT_LOCAL_MACHINE) so both SYSTEM (scheduled
task) and interactive Admin sessions can decrypt it.

- Resolves the password from the bootstrap source (scratch/live_apply_ttl.py).
- Verifies it against POST /api/auth/login BEFORE touching the vault.
- Never prints the secret.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

import requests
from password_vault import store_password, retrieve_password


def resolve_bootstrap() -> str:
    p = ROOT / "scratch" / "live_apply_ttl.py"
    m = re.search(r'or\s+"([^"]{8,})"', p.read_text(encoding="utf-8", errors="replace"))
    if not m:
        raise SystemExit("bootstrap literal not found")
    return m.group(1)


def main() -> int:
    pw = resolve_bootstrap()
    # Verify against live login endpoint first
    r = requests.post(
        "http://127.0.0.1:20128/api/auth/login",
        json={"password": pw},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"[-] login verification FAILED: HTTP {r.status_code}; vault NOT touched")
        return 1
    print("[+] password verified against /api/auth/login (200)")

    # Re-store with machine-scoped DPAPI
    path = store_password(pw)
    print(f"[+] vault re-stored (machine scope) at {path}")

    # Verify roundtrip from THIS session
    dec = retrieve_password()
    if dec == pw:
        print("[+] retrieve_password() roundtrip OK from interactive session")
    else:
        print("[-] roundtrip MISMATCH")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
