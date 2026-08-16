#!/usr/bin/env python3
"""Inspect browser storage_state.json freshness + per-domain cookie presence (T11: no values printed)."""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
path = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")

if not os.path.exists(path):
    print("storage_state.json NOT FOUND")
    sys.exit(1)

mtime = os.path.getmtime(path)
age_h = (time.time() - mtime) / 3600
print(f"storage_state.json last modified: {datetime.fromtimestamp(mtime)} ({age_h:.1f} h ago)")

data = json.load(open(path, encoding="utf-8"))
cookies = data.get("cookies", [])
origins = data.get("origins", [])
print(f"cookies: {len(cookies)}, origins (localStorage): {len(origins)}")

targets = ["openrouter.ai", "anthropic.com", "github.com", "console.anthropic.com"]
now = time.time()
by_domain = {}
for c in cookies:
    d = c.get("domain", "")
    by_domain.setdefault(d, []).append(c)

print("\nPer-domain cookie summary (names only, values redacted):")
for t in targets:
    matches = {d: cs for d, cs in by_domain.items() if t in d}
    if not matches:
        print(f"  {t}: NO COOKIES")
        continue
    for d, cs in matches.items():
        names = sorted({c.get("name", "?") for c in cs})
        expired = sum(1 for c in cs if 0 < c.get("expires", -1) < now)
        sessionish = [n for n in names if any(k in n.lower() for k in ("session", "auth", "token", "sid", "logged"))]
        print(f"  {d}: {len(cs)} cookies, {expired} expired; auth-ish names: {sessionish or 'none'}")

print("\nlocalStorage origins:")
for o in origins[:20]:
    ls = o.get("localStorage", [])
    print(f"  {o.get('origin')}: {len(ls)} items")
