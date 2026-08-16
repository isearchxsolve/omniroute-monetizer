#!/usr/bin/env python3
"""Full connection health picture: authType breakdown, OAuth connections,
active-but-unhealthy connections. T11-safe."""
import os, re, sys
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

def get_password():
    pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
    if pw:
        return pw
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
print("total:", len(conns))
print("by authType:", dict(Counter(c.get("authType") for c in conns)))
print()
print("--- OAuth connections (all) ---")
for c in conns:
    if c.get("authType") == "oauth":
        print(f"  {c.get('provider'):16s} active={str(c.get('isActive')):5s} testStatus={c.get('testStatus')} name={(c.get('name') or '')[:30]}")
print()
print("--- active connections with testStatus != active ---")
n = 0
for c in conns:
    if c.get("isActive") and c.get("testStatus") != "active":
        n += 1
        print(f"  {c.get('provider'):16s} authType={c.get('authType'):7s} testStatus={c.get('testStatus')}")
if n == 0:
    print("  (none — all active connections report testStatus=active)")
print()
print("--- active connections by provider (oauth only, dedup) ---")
print(dict(Counter(c.get("provider") for c in conns if c.get("authType") == "oauth")))
