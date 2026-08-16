#!/usr/bin/env python3
"""Sync llm7 models + inspect codex auth tokens structure (no secret values)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()
conns = api.get_connections()
llm7 = [c for c in conns if c.get("provider") == "llm7"]
if llm7:
    cid = llm7[0]["id"]
    r = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
    print("llm7 sync:", r.status_code, r.text[:200])
else:
    print("llm7 connection not found")

# codex auth.json structure
p = os.path.expanduser("~/.codex/auth.json")
d = json.load(open(p))
tok = d.get("tokens") or {}
print("codex tokens keys:", list(tok.keys()))
for k, v in tok.items():
    if isinstance(v, str):
        print(f"  {k}: [set, len={len(v)}, prefix={v[:6]}...]")
    elif isinstance(v, (int, float)):
        print(f"  {k}: {v}")
    else:
        print(f"  {k}: {type(v).__name__}")
print("auth_mode:", d.get("auth_mode"))
