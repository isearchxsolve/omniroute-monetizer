#!/usr/bin/env python3
"""
Fix G2: Deactivate the dead auto/zai combo.

Purpose:
  POST_AUDIT_GAPS G2 — the zai family has zero connected models, so every
  auto-combo pool rebuild walks it, adding to the rebuild cost that freezes the
  event loop ~24-38s (worklog #23). Deactivating it skips the walk.

Ground rules:
  - Supported API only (GET /api/combos, PUT /api/combos/{id}).
  - Idempotent: already-deactivated combos are left untouched.
  - Never restarts the service; no DB access.

Output:
  state/zai_deactivation_report.json (redacted)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact, save_json, log


def run_deactivate(dry_run: bool = False) -> Dict[str, Any]:
    api = OmniRouteAPI()
    if not api.login():
        log("Management login failed; aborting", "err")
        return {"status": "AUTH_FAILED"}

    combos = api.get_combos()
    zai = [c for c in combos if "zai" in str(c.get("name", "")).lower()]
    if not zai:
        log("No auto/zai combo found — nothing to do", "skip")
        return {"status": "NO_ZAI_COMBO", "combos_evaluated": len(combos)}

    changed, skipped = [], []
    for c in zai:
        cid, cname = c.get("id"), c.get("name", "")
        if not c.get("isActive", True):
            skipped.append({"combo": cname, "reason": "already_inactive"})
            continue
        if dry_run:
            log(f"[dry-run] would deactivate {cname} ({cid})", "info")
            changed.append({"combo": cname, "dry_run": True})
            continue
        res = api.update_combo(cid, {"isActive": False})
        if res.get("http_status") == 200:
            log(f"Deactivated dead combo {cname} ({cid})", "ok")
            changed.append({"combo": cname, "http": 200})
        else:
            log(f"Deactivation failed for {cname}: HTTP {res.get('http_status')}", "err")
            skipped.append({"combo": cname, "reason": f"update_failed {res.get('http_status')}"})

    report = {
        "timestamp": dt.datetime.now().isoformat(),
        "dry_run": dry_run,
        "combos_evaluated": len(combos),
        "zai_combos_found": len(zai),
        "deactivated": changed,
        "skipped": skipped,
        "verdict": "DEACTIVATED" if changed else "NO_CHANGES",
    }
    path = save_json("zai_deactivation_report.json", report)
    log(f"Report saved: {path}", "ok")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="G2 deactivate dead auto/zai combo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_deactivate(dry_run=args.dry_run)
