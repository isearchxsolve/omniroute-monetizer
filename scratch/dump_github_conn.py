#!/usr/bin/env python3
"""Dump full GitHub connection object (T11-safe: masks any secret-looking values)."""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRATCH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

SECRET_RE = re.compile(r"(gh[opsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{16,}|Bearer\s+[A-Za-z0-9_\-\.]{16,})", re.I)

def redact_obj(o):
    if isinstance(o, dict):
        return {k: redact_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [redact_obj(v) for v in o]
    if isinstance(o, str):
        return SECRET_RE.sub("[REDACTED]", o)
    return o

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
api = OmniRouteAPI(password=get_password())
api.login()
conns = api.get_connections()
for c in conns:
    if (c.get("provider") or "").lower() == "github":
        print(json.dumps(redact_obj(c), indent=2, ensure_ascii=False))
