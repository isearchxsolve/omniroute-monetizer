#!/usr/bin/env python3
"""List OmniRoute connections matching a provider keyword (T11-safe: masks keys)."""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRATCH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

def get_password():
    pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
    if pw:
        return pw
    for name in ("raise_catalog_ttl.py", "live_apply_ttl.py"):
        path = os.path.join(SCRATCH, name)
        if not os.path.exists(path):
            continue
        try:
            content = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        m = re.search(r'or\s+"([^"]{8,})"', content)
        if m:
            return m.group(1)
    return ""

from omniroute_api import OmniRouteAPI

kw = sys.argv[1] if len(sys.argv) > 1 else ""
api = OmniRouteAPI(password=get_password())
api.login()
conns = api.get_connections()
print(f"total connections: {len(conns)}")
for c in conns:
    prov = (c.get("provider") or "")
    name = (c.get("name") or "")
    if kw and kw.lower() not in prov.lower() and kw.lower() not in name.lower():
        continue
    key = c.get("apiKey") or ""
    masked = (key[:8] + "..." + key[-4:]) if len(key) > 14 else ("<empty>" if not key else "[short]")
    print(f"  id={c.get('id')} provider={prov!r} name={name!r} authType={c.get('authType')} active={c.get('isActive')} key={masked}")
