#!/usr/bin/env python3
"""Test OmniRoute's NATIVE OAuth refresh endpoint on one healthy OAuth connection.
This is the correct abstraction-layer mechanism (anti-pattern #1) vs the broken
inference-ping daemon. Read-only-ish: refresh rotates the token server-side."""
import os, re, sys, json
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

# pick healthy active oauth connections to test refresh on
candidates = [c for c in conns if c.get("authType") == "oauth" and c.get("isActive") and c.get("testStatus") == "active"]
print(f"healthy active oauth connections: {len(candidates)}")
for c in candidates:
    print(f"  {c['id']} {c.get('provider')}")

if not candidates:
    print("no healthy oauth connection to test")
    sys.exit(1)

# test refresh on the first one
target = candidates[0]
print(f"\n[*] testing POST /api/providers/{target['id']}/refresh (provider={target.get('provider')}) ...")
res = api.refresh_connection(target["id"])
http = res.get("http_status")
body = res.get("result")
# redact secrets from body
SECRET_RE = re.compile(r"(gh[opsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{16,}|tid=[a-f0-9]{32}|Bearer\s+[A-Za-z0-9_\-\.]{16,})", re.I)
body_str = SECRET_RE.sub("[REDACTED]", json.dumps(body)[:600]) if isinstance(body, (dict, list)) else str(body)[:300]
print(f"[*] refresh -> HTTP {http}")
print(f"[*] body: {body_str}")

# re-test the connection after refresh
test = api.test_connection(target["id"])
print(f"[*] post-refresh test_connection -> HTTP {test.get('http_status')} result={json.dumps(test.get('result'))[:300]}")
