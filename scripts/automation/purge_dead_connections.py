#!/usr/bin/env python3
"""
Fix P5: Purge dead OAuth connections via SUPPORTED API only (no DB access).

Purpose:
  Remove the ~30 suppressed (isActive=false) dead connections that waste
  decryption/network work in every sweep (POST_AUDIT_GAPS P5).

Ground rules (AGENTS.md):
  - NEVER touch storage.sqlite directly. Only /api endpoints.
  - DELETE /api/providers/{id} is probed first; if unsupported, the script
    reports "no supported delete path" and takes NO destructive action.
  - isActive=false suppression is preserved as the safe fallback.

Output:
  state/purge_report.json (redacted)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact, save_json, log


def _delete_probe(api: OmniRouteAPI) -> Dict[str, Any]:
    """Probe whether DELETE /api/providers/{id} is supported WITHOUT side effects.

    Sends DELETE to a non-existent UUID. The real row is never touched:
      - HTTP 405 / 501  -> method not supported (expected on 3.8.49)
      - HTTP 404        -> endpoint exists, id not found (DELETE IS supported)
      - HTTP 200 / 204  -> endpoint exists and accepts (also supported)
    """
    probe_id = "00000000-0000-0000-0000-000000000000"
    try:
        r = api.session.delete(f"{api.api}/providers/{probe_id}", timeout=15)
        return {"probe_id": probe_id, "http_status": r.status_code,
                "body": redact(r.text[:300])}
    except Exception as e:
        return {"probe_id": probe_id, "http_status": None,
                "error": f"{type(e).__name__}: {e}"}


def run_purge(dry_run: bool = False) -> Dict[str, Any]:
    api = OmniRouteAPI()
    if not api.login():
        log("Management login failed; aborting", "err")
        return {"status": "AUTH_FAILED"}

    conns = api.get_connections()
    dead = [c for c in conns if not c.get("isActive", True)]
    active = [c for c in conns if c.get("isActive", True)]
    log(f"Connections: {len(conns)} total, {len(active)} active, {len(dead)} suppressed/dead")

    # Step 1: re-test a sample of dead connections to confirm still failing
    still_dead, revived = [], []
    for c in dead:
        res = api.test_connection(c["id"])
        valid = bool(res.get("result", {}).get("valid"))
        if valid:
            revived.append({"id": c["id"], "provider": c.get("provider")})
        else:
            still_dead.append({"id": c["id"], "provider": c.get("provider"),
                               "reason": redact(str(res.get("result")))[:160]})
    log(f"Re-tested: {len(dead)} dead candidates -> {len(revived)} revived, {len(still_dead)} still dead")

    # Step 2: probe DELETE support on a non-existent UUID (no side effects)
    delete_supported = False
    delete_probe = None
    probe = _delete_probe(api)
    delete_probe = {"response": probe}
    delete_supported = probe.get("http_status") in (200, 204, 404)
    log(f"DELETE /api/providers/{{id}} probe: HTTP {probe.get('http_status')} "
        f"-> {'SUPPORTED' if delete_supported else 'NOT SUPPORTED (expected on 3.8.49)'}",
        "ok" if delete_supported else "warn")

    # Step 3: act
    purged, kept = [], []
    if delete_supported and still_dead and not dry_run:
        for c in still_dead:
            r = api.session.delete(f"{api.api}/providers/{c['id']}", timeout=15)
            if r.status_code in (200, 204):
                purged.append(c["id"])
            else:
                kept.append({"id": c["id"], "http": r.status_code})
        log(f"Purged {len(purged)} dead connections via supported DELETE")
    else:
        kept = still_dead
        log("No supported delete path on this version; keeping suppressed "
            "(isActive=false) — safe, documented outcome.", "skip")

    report = {
        "timestamp": dt.datetime.now().isoformat(),
        "dry_run": dry_run,
        "totals": {"connections": len(conns), "active": len(active), "dead": len(dead)},
        "retest": {"revived": revived, "still_dead": len(still_dead)},
        "delete_support_probe": delete_probe,
        "delete_supported": delete_supported,
        "purged_ids": purged,
        "kept_ids": kept,
        "outcome": ("PURGED" if purged else
                    "NO_SUPPORTED_DELETE_PATH" if not delete_supported else
                    "DRY_RUN"),
    }
    path = save_json("purge_report.json", report)
    log(f"Report saved: {path}", "ok")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P5 purge dead OAuth connections (supported API only)")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no DELETE")
    args = parser.parse_args()
    run_purge(dry_run=args.dry_run)
