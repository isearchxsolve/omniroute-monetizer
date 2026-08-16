#!/usr/bin/env python3
"""Provision untried zero-auth/free catalog providers, verify upstream, keep only valid ones active.

Zero-fabrication: a provider counts ONLY if POST /api/providers/{id}/test returns valid=true.
Invalid ones are deactivated immediately.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI

# Untried free/no-key slugs from the catalog scan
CANDIDATES = [
    "gemini-web", "huggingchat", "qwen-web", "t3-web", "yuanbao-web",
    "zenmux-free", "freeaiapikey", "freemodel-dev", "freetheai", "freepik",
]

api = OmniRouteAPI()
if not api.login():
    sys.exit(1)

conns = api.get_connections()
existing = {c.get("provider"): c for c in conns}

results = []
for slug in CANDIDATES:
    if slug in existing:
        print(f"  {slug:16} already has connection, skipping create")
        continue
    payload = {
        "provider": slug,
        "name": f"{slug} (zero-auth)",
        "authType": "none",
        "isActive": True,
        "apiKey": "",
    }
    r = api.session.post(f"{api.api}/providers", json=payload, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  {slug:16} create HTTP {r.status_code}: {r.text[:90]}")
        results.append((slug, "rejected", None))
        continue
    body = r.json()
    conn = body.get("connection") or body
    cid = conn.get("id")
    print(f"  {slug:16} created {cid[:8]}")

    # sync models
    rs = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
    sync_ok = rs.status_code == 200
    synced = ""
    if sync_ok:
        try:
            synced = f" models={rs.json().get('syncedModels')}"
        except Exception:
            pass
    # test upstream
    t0 = time.time()
    res = api.test_connection(cid)
    dt = int((time.time() - t0) * 1000)
    result = res.get("result", {}) or {}
    valid = bool(result.get("valid"))
    diag = result.get("diagnosis", "")
    if isinstance(diag, dict):
        diag = diag.get("type", "")
    print(f"  {slug:16} sync={rs.status_code}{synced} test valid={valid} {dt}ms diag={str(diag)[:50]}")
    if not valid:
        api.session.put(f"{api.api}/providers/{cid}", json={"isActive": False}, timeout=30)
        print(f"  {slug:16} deactivated (not upstream-verified)")
    results.append((slug, "valid" if valid else "invalid", dt))

ok = [s for s, st, _ in results if st == "valid"]
print(f"\nSUMMARY: valid={ok or 'none'} | rejected={[s for s,st,_ in results if st=='rejected']}")
