"""Restart OmniRoute via its own management API (no OS admin needed).

The NSSM-managed node process exits on the self-restart call and NSSM
respawns it, clearing the in-process turbopack external-module cache that
was holding the stale playwright load failure.
"""
import sys, time, json
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()
print("[+] Management login OK")

# Try the self-restart endpoint. POST first, fall back to GET.
resp = None
for method in ("post", "get"):
    fn = getattr(api.session, method)
    try:
        r = fn(f"{api.api}/version-manager/restart", timeout=15)
        print(f"[{method.upper()}] /api/version-manager/restart -> HTTP {r.status_code}")
        print("    body:", r.text[:300])
        if r.status_code < 500:
            resp = r
            break
    except Exception as e:
        print(f"[{method.upper()}] failed: {e}")

if resp is None:
    print("[-] could not trigger self-restart")
    sys.exit(1)

# Wait for the service to go down then come back up.
base = api.base if hasattr(api, "base") else "http://localhost:20128"
import requests
print("[*] waiting for service to drop...")
down = False
for _ in range(30):
    try:
        requests.get(base + "/healthz", timeout=2)
    except Exception:
        down = True
        break
    time.sleep(1)
print("    down:", down)

print("[*] waiting for service to come back...")
up = False
for i in range(60):
    try:
        r = requests.get(base + "/healthz", timeout=2)
        if r.status_code < 500:
            up = True
            print(f"    UP after ~{i}s -> HTTP {r.status_code}")
            break
    except Exception:
        pass
    time.sleep(1)

if not up:
    print("[-] service did not come back within 60s")
    sys.exit(2)

print("[+] restart complete")
