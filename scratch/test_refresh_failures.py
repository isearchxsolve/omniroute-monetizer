#!/usr/bin/env python3
"""Test connections that failed refresh to see if they're still usable.
'refresh failed' may not mean 'connection dead' (e.g. GitHub Copilot tokens
refresh via a different internal path). T11-safe."""
import os, re, sys, json
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

def get_password():
    pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
    if pw:
        return pw
    pf = os.path.join(ROOT, "state", "omniroute_password.txt")
    if os.path.exists(pf):
        return open(pf, encoding="utf-8").read().strip()
    for name in ("raise_catalog_ttl.py", "live_apply_ttl.py"):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        if not os.path.exists(p):
            continue
        m = re.search(r'or\s+"([^"]{8,})"', open(p, encoding="utf-8", errors="replace").read())
        if m:
            return m.group(1)
    return ""

from omniroute_api import OmniRouteAPI

api = OmniRouteAPI(password=get_password())
api.login()
conns = api.get_connections()

# the 5 that failed refresh
failed_providers = ["github", "trae", "windsurf", "kilocode"]
targets = [c for c in conns if c.get("authType") == "oauth" and c.get("isActive") and c.get("provider") in failed_providers]
print(f"testing {len(targets)} refresh-failed active connections:\n")
for c in targets:
    test = api.test_connection(c["id"])
    http = test.get("http_status")
    res = test.get("result") or {}
    valid = res.get("valid")
    diag = (res.get("diagnosis") or {})
    err = res.get("error")
    lat = res.get("latencyMs")
    print(f"  {c.get('provider'):12s} id={c['id'][:8]} valid={valid} latency={lat}ms diag={diag.get('type')}/{diag.get('source')} err={str(err)[:80]}")
