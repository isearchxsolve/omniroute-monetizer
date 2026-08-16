#!/usr/bin/env python3
"""
OmniRoute Hot-Reload Combo Optimizer (COMPLETE)

Populates the core routing combos with verified live models, enforcing the
Performance Invariant from AGENTS.md:

  Ultra-low latency, tool-call-verified models (nvidia/nemotron-3-super-120b-a12b,
  nvidia/nemotron-nano-12b-v2-vl, ~2-3.5s TTFT) are placed as Priority #1 in all
  core combos so clients never time out, cascading to higher-tier models.

Safety rules:
- NEVER restarts OmniRoute; only GET/PUT on /api/combos.
- Non-destructive: models that fail a live probe are demoted to the tail of the
  cascade, never deleted (idempotent + no data loss).
- Combos are only PUT when the ordering actually changes.
- Never uses llama-3.1-nemotron-nano-vl-8b-v1 as the sole/priority head for
  coding/agent combos (it rejects tool_choice:"auto" with 400).
- All artifacts redacted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from omniroute_api import OmniRouteAPI, log, save_json  # noqa: E402

# Tool-safe, ultra-low-latency priority heads (AGENTS.md Performance Invariant)
TOOL_SAFE_PRIORITY_HEADS = [
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-nano-12b-v2-vl",
]

# Models that must NOT be priority heads for agent/coding combos
BAD_AGENT_HEADS = {
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",  # rejects tool_choice:"auto"
}

CORE_COMBOS = [
    "frontier",
    "auto/pro-coding",
    "auto/pro-reasoning",
    "auto/pro-chat",
    "auto/best-coding",
    "auto/best-reasoning",
    "auto/best-chat",
    "fusion-coder",
    "kimi-coding",
    "moonshotai/kimi-k3-free",
]


def probe_models(api: OmniRouteAPI, models: List[str], timeout: int = 30) -> Dict[str, Dict[str, Any]]:
    """One valid live probe per unique model (no mass probing, no tiny payloads)."""
    results: Dict[str, Dict[str, Any]] = {}
    for m in models:
        log(f"Probing {m} ...")
        r = api.chat_probe(m, timeout=timeout)
        results[m] = r
        if r["ok"]:
            log(f"  VERIFIED {m} ({r['latency']}s)", "ok")
        else:
            log(f"  FAILED {m}: {r.get('error') or r.get('http_status')}", "warn")
    return results


def desired_order(current_models: List[Dict[str, Any]],
                  probes: Dict[str, Dict[str, Any]],
                  is_agent_combo: bool) -> List[Dict[str, Any]]:
    """Reorder a combo's model entries: verified tool-safe heads first.

    Non-destructive: failed/unprobed models are kept at the tail in their
    original relative order.
    """
    by_model = {m.get("model"): m for m in current_models if m.get("model")}
    verified = {name for name, p in probes.items() if p.get("ok")}
    latency = {name: p.get("latency") or 999.0 for name, p in probes.items()}

    ordered_names: List[str] = []

    # 1) tool-safe priority heads (only for agent/coding combos, or if they are
    #    the only verified options for non-agent combos)
    if is_agent_combo:
        for head in TOOL_SAFE_PRIORITY_HEADS:
            if head in by_model and head in verified:
                ordered_names.append(head)

    # 2) remaining verified models by latency
    rest = [n for n in by_model if n in verified and n not in ordered_names]
    if is_agent_combo:
        rest = [n for n in rest if n not in BAD_AGENT_HEADS or len(verified) <= 1]
    rest.sort(key=lambda n: latency.get(n, 999.0))
    ordered_names.extend(rest)

    # 3) demoted (unverified) models keep original relative order at the tail
    tail = [m.get("model") for m in current_models
            if m.get("model") and m.get("model") not in ordered_names]
    ordered_names.extend(tail)

    # de-dup safety
    seen = set()
    final = []
    for n in ordered_names:
        if n not in seen and n in by_model:
            seen.add(n)
            final.append(by_model[n])
    return final


def main() -> int:
    p = argparse.ArgumentParser(description="OmniRoute combo hot-reload optimizer")
    p.add_argument("--dry-run", action="store_true", help="compute ordering, no PUT")
    p.add_argument("--probe-timeout", type=int, default=30)
    args = p.parse_args()

    log("=== COMBO OPTIMIZER: HOT-RELOAD ===")
    api = OmniRouteAPI()
    if not api.login():
        log("Cannot authenticate; aborting optimizer", "err")
        return 1

    connections = api.get_connections()
    combos = api.get_combos()
    active_conns = [c for c in connections if c.get("isActive") and c.get("testStatus") == "active"]
    log(f"Connections: {len(connections)} total, {len(active_conns)} active+healthy")
    log(f"Combos: {len(combos)}")

    named = [c for c in combos if c.get("name") and c.get("id")]
    orphaned = [c for c in combos if not c.get("id")]
    if orphaned:
        log(f"Found {len(orphaned)} orphaned combo entries without ids (not updatable via API)", "warn")

    # Collect unique models across named combos
    unique_models = []
    seen = set()
    for c in named:
        for m in c.get("models", []):
            mid = m.get("model")
            if mid and mid not in seen:
                seen.add(mid)
                unique_models.append(mid)
    log(f"Unique models across named combos: {len(unique_models)}")

    probes = probe_models(api, unique_models, timeout=args.probe_timeout)
    verified = [m for m, r in probes.items() if r.get("ok")]
    log(f"Verified live models: {len(verified)} / {len(unique_models)}")

    changes = []
    for c in named:
        name = c.get("name")
        cid = c.get("id")
        models = c.get("models", [])
        if not models:
            log(f"{name}: empty combo, skipping (no models to order)", "skip")
            continue
        is_agent = name in CORE_COMBOS
        new_models = desired_order(models, probes, is_agent_combo=is_agent)
        current_seq = [m.get("model") for m in models]
        new_seq = [m.get("model") for m in new_models]
        if current_seq == new_seq:
            log(f"{name}: ordering already optimal, no change (idempotent)", "skip")
            continue

        payload = dict(c)
        payload["models"] = new_models
        change = {
            "combo": name,
            "id": cid,
            "before": current_seq,
            "after": new_seq,
        }
        if args.dry_run:
            change["applied"] = False
            log(f"{name}: DRY-RUN would reorder -> {new_seq[:3]}...", "info")
        else:
            res = api.update_combo(cid, payload)
            change["applied"] = res.get("http_status") == 200
            change["http_status"] = res.get("http_status")
            if change["applied"]:
                log(f"{name}: UPDATED priority heads -> {new_seq[:2]}", "ok")
            else:
                log(f"{name}: PUT failed HTTP {res.get('http_status')}", "err")
        changes.append(change)

    # Post-update verification of core aliases (one probe each)
    post_verify = {}
    if not args.dry_run:
        for alias in ["frontier", "auto/pro-coding", "auto/pro-reasoning", "auto/pro-chat"]:
            r = api.chat_probe(alias, timeout=40)
            post_verify[alias] = r
            log(f"Post-verify {alias}: {'OK' if r['ok'] else 'FAIL'} "
                f"({r.get('latency')}s, resolved={r.get('response_model')})",
                "ok" if r["ok"] else "err")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": args.dry_run,
        "connections_total": len(connections),
        "connections_active": len(active_conns),
        "combos_total": len(combos),
        "combos_named": len(named),
        "combos_orphaned": len(orphaned),
        "models_probed": len(unique_models),
        "models_verified": verified,
        "changes": changes,
        "post_verify": post_verify,
    }
    save_json("combo_optimization.json", report)
    log(f"Optimizer complete: {len(changes)} combo(s) changed", "ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
