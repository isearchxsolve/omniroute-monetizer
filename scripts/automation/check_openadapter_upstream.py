"""Check openadapter provider definition and models in OmniRoute / upstream.
"""
from __future__ import annotations
import sys
import json
import pathlib
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import KEYS_FILE, fingerprint

sys.stdout.reconfigure(encoding="utf-8")

def check_openadapter():
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    # Read generated keys if present
    key = None
    if KEYS_FILE.exists():
        try:
            keys = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            key = keys.get("openadapter")
        except Exception:
            pass
            
    print(f"[+] Loaded openadapter key: {fingerprint(key) if key else 'None'}")
    
    # Check what models OpenAdapter upstream API exposes
    if key:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            r = requests.get("https://api.openadapter.in/v1/models", headers=headers, timeout=10)
            print(f"[+] Upstream GET https://api.openadapter.in/v1/models -> HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"    Total models: {len(data.get('data', []))}")
                for m in data.get("data", [])[:10]:
                    print(f"    - {m.get('id')}")
            else:
                print(f"    Body: {r.text[:300]}")
        except Exception as exc:
            print(f"[-] Upstream models fetch failed: {exc}")

if __name__ == "__main__":
    check_openadapter()
