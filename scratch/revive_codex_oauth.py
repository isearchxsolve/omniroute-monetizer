#!/usr/bin/env python3
"""Inspect codex connection shape, then try injecting the local ChatGPT OAuth
access token from ~/.codex/auth.json. Verify upstream; revert if invalid."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, mask_token

api = OmniRouteAPI()
api.login()
conns = api.get_connections()
codex = [c for c in conns if c.get("provider") == "codex"]
for c in codex:
    psd = c.get("providerSpecificData") or {}
    print(f"codex conn {c['id'][:8]}: authType={c.get('authType')} isActive={c.get('isActive')} "
          f"lastError={c.get('lastError')} psd_keys={list(psd.keys())}")
    for k, v in psd.items():
        if isinstance(v, str) and len(v) > 20:
            print(f"    psd.{k}: [set, len={len(v)}, prefix={v[:8]}...]")
        else:
            print(f"    psd.{k}: {v!r}")

if not codex:
    print("no codex connection")
    sys.exit(0)

auth = json.load(open(os.path.expanduser("~/.codex/auth.json")))
tok = auth.get("tokens") or {}
access = tok.get("access_token", "")
refresh = tok.get("refresh_token", "")
print(f"\nlocal codex token: access={mask_token(access)} refresh={mask_token(refresh)}")

cid = codex[0]["id"]
# Try injecting as OAuth-style providerSpecificData first, then plain apiKey
attempts = [
    ("psd-oauth", {"providerSpecificData": {"access_token": access, "refresh_token": refresh,
                                            "account_id": tok.get("account_id", ""),
                                            "id_token": tok.get("id_token", "")}, "isActive": True}),
    ("apikey", {"apiKey": access, "isActive": True}),
]
for label, payload in attempts:
    r = api.session.put(f"{api.api}/providers/{cid}", json=payload, timeout=30)
    print(f"\nattempt {label}: HTTP {r.status_code} {r.text[:120]}")
    if r.status_code != 200:
        continue
    t0 = time.time()
    res = api.test_connection(cid)
    dt = int((time.time() - t0) * 1000)
    result = res.get("result", {}) or {}
    valid = bool(result.get("valid"))
    diag = result.get("diagnosis", "")
    if isinstance(diag, dict):
        diag = diag.get("type", "")
    print(f"attempt {label}: valid={valid} {dt}ms diag={str(diag)[:60]}")
    if valid:
        print(f"SUCCESS: codex revived via {label}")
        break
else:
    # revert to inactive
    api.session.put(f"{api.api}/providers/{cid}", json={"isActive": False}, timeout=30)
    print("\ncodex still dead — reverted inactive (zero-fabrication)")
