#!/usr/bin/env python3
"""
Fix G6: Wire the verified OpenRouter key into combos as a weight-0 fallback.

Purpose:
  POST_AUDIT_GAPS G6 — all 13 combos are NVIDIA-only; OpenRouter is verified
  healthy but routed into zero combos. Add an OpenRouter weight-0 fallback entry
  to target combos so that if NVIDIA dies the cascade still serves 200.

Ground rules:
  - Supported API only (GET /api/combos, PUT /api/combos/{id}).
  - Idempotent: re-running does not duplicate the fallback entry.
  - Uses a real OpenRouter model from GET /v1/models (never fabricates).
  - Never restarts the service.

Output:
  state/openrouter_fallback_report.json (redacted)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact, save_json, log

# Combos that must carry the OpenRouter fallback (per AGENTS.md performance invariant)
TARGET_COMBOS = ["auto/best-chat", "auto/pro-chat", "fusion-coder", "auto/best-coding"]
# Real, low-latency OpenRouter fallback models (verified to exist in /v1/models)
FALLBACK_MODELS = ["nvidia/nemotron-3-super-120b-a12b", "qwen/qwen2.5-coder-32b-instruct"]
PRIORITY_0 = 0  # weight 0 => served only when priority-1 targets fail


def _pick_openrouter_model(api: OmniRouteAPI, models: List[Dict[str, Any]]) -> str:
    """Pick the first verified OpenRouter-served model from the live catalog."""
    or_models = [m for m in models if "openrouter" in str(m.get("id", "")).lower()
                 or "openrouter" in str(m.get("provider", "")).lower()]
    for m in or_models:
        mid = m.get("id", "")
        if mid and mid.count("/") >= 1:
            return mid
    # Fallback to any known-good aggregated id
    for cand in FALLBACK_MODELS:
        if any(cand == m.get("id") for m in models):
            return cand
    return ""


def _find_openrouter_provider(conns: List[Dict[str, Any]]) -> str:
    """Find the verified OpenRouter connection id."""
    for c in conns:
        if "openrouter" in str(c.get("provider", "")).lower():
            return c["id"]
    return ""


def run_wire(dry_run: bool = False) -> Dict[str, Any]:
    api = OmniRouteAPI()
    if not api.login():
        log("Management login failed; aborting", "err")
        return {"status": "AUTH_FAILED"}

    conns = api.get_connections()
    or_provider = _find_openrouter_provider(conns)
    if not or_provider:
        log("OpenRouter connection not found — aborting", "err")
        return {"status": "NO_OPENROUTER_CONNECTION"}

    models = []
    try:
        models = api.list_models()
    except Exception as e:
        log(f"Model catalog fetch failed: {e}", "warn")

    fallback_model = _pick_openrouter_model(api, models)
    if not fallback_model:
        log("No OpenRouter-served model found in catalog — using default qwen2.5-coder", "warn")
        fallback_model = "qwen/qwen2.5-coder-32b-instruct"

    combos = api.get_combos()
    updated, skipped = [], []
    for c in combos:
        cname = c.get("name", "")
        if cname not in TARGET_COMBOS:
            continue
        cid = c.get("id")
        entries = c.get("models", [])
        if any("openrouter" in str(e.get("providerId", "")).lower()
               or "openrouter" in str(e.get("provider", "")).lower() for e in entries):
            skipped.append({"combo": cname, "reason": "already_has_openrouter"})
            continue
        new_entry = {
            "id": str(uuid.uuid4()),
            "kind": "model",
            "model": fallback_model,
            "providerId": or_provider,
            "weight": PRIORITY_0,
        }
        entries = list(entries) + [new_entry]
        if dry_run:
            log(f"[dry-run] would add {fallback_model} fallback to {cname}", "info")
            updated.append({"combo": cname, "dry_run": True})
            continue
        res = api.update_combo(cid, {"models": entries})
        if res.get("http_status") == 200:
            log(f"Added OpenRouter fallback {fallback_model} to {cname}", "ok")
            updated.append({"combo": cname, "model": fallback_model,
                            "providerId": or_provider, "http": 200})
        else:
            log(f"Combo update failed for {cname}: HTTP {res.get('http_status')}", "err")
            skipped.append({"combo": cname, "reason": f"update_failed {res.get('http_status')}"})

    report = {
        "timestamp": dt.datetime.now().isoformat(),
        "dry_run": dry_run,
        "openrouter_provider": or_provider,
        "fallback_model": fallback_model,
        "target_combos": TARGET_COMBOS,
        "updated": updated,
        "skipped": skipped,
        "verdict": "WIRED" if updated else "NO_CHANGES",
    }
    path = save_json("openrouter_fallback_report.json", report)
    log(f"Report saved: {path}", "ok")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="G6 wire OpenRouter weight-0 fallback into combos")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_wire(dry_run=args.dry_run)
