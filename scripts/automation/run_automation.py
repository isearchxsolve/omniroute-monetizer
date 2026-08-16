#!/usr/bin/env python3
"""
Provider Automation Orchestrator — end-to-end Monetizer automation runner.

Runs the three-tier blueprint in order:
  Tier 1: CLI/runtime token harvest + upstream verification + hot-injection
  Tier 2: (optional) browser key-generation adapters  [--tier2]
  Tier 3: combo hot-reload optimization + post-verification

Safety: never restarts OmniRoute; idempotent; all artifacts redacted.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from omniroute_api import OmniRouteAPI, log, save_json  # noqa: E402

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run_module(module: str, extra: list[str]) -> dict:
    cmd = [PY, str(HERE / module), *extra]
    log(f"Running: {module} {' '.join(extra)}")
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        out = (proc.stdout or "") + (proc.stderr or "")
        # redact: never persist raw output that could contain secrets
        return {
            "module": module,
            "returncode": proc.returncode,
            "elapsed": round(time.monotonic() - start, 2),
            "tail": out[-2000:],
        }
    except Exception as e:
        return {"module": module, "returncode": None, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    p = argparse.ArgumentParser(description="End-to-end automation orchestrator")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--tier2", action="store_true", help="also run browser key-gen adapters")
    p.add_argument("--tier2-providers", default="", help="comma list for tier2 (github,anthropic,openrouter)")
    args = p.parse_args()

    log("=== ORCHESTRATOR: END-TO-END AUTOMATION ===")
    results = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "dry_run": args.dry_run, "tiers": {}}

    # Preflight: confirm live runtime (never restart)
    api = OmniRouteAPI()
    try:
        models = api.list_models()
        log(f"Preflight: OmniRoute reachable, {len(models)} models", "ok")
        results["preflight"] = {"reachable": True, "models": len(models)}
    except Exception as e:
        log(f"Preflight FAILED: {e}", "err")
        results["preflight"] = {"reachable": False, "error": str(e)}
        save_json("orchestrator_result.json", results)
        return 1

    # Tier 1
    t1_extra = ["--dry-run"] if args.dry_run else []
    results["tiers"]["tier1_harvest"] = run_module("cli_token_harvester.py", t1_extra)

    # Tier 2 (optional, browser)
    if args.tier2:
        providers = [x.strip() for x in args.tier2_providers.split(",") if x.strip()] or ["openrouter"]
        t2 = []
        for prov in providers:
            extra = [prov] + (["--no-inject"] if args.dry_run else [])
            t2.append(run_module("provider_key_adapters.py", extra))
        results["tiers"]["tier2_keygen"] = t2
    else:
        log("Tier 2 (browser key-gen) skipped (use --tier2 to enable)", "skip")

    # Tier 3: combo optimization
    t3_extra = ["--dry-run"] if args.dry_run else []
    results["tiers"]["tier3_combo_optimizer"] = run_module("combo_optimizer.py", t3_extra)

    save_json("orchestrator_result.json", results)

    # Summary
    ok = True
    for tier, res in results["tiers"].items():
        entries = res if isinstance(res, list) else [res]
        for e in entries:
            rc = e.get("returncode")
            status = "OK" if rc == 0 else f"FAIL(rc={rc})"
            if rc != 0:
                ok = False
            log(f"{tier}: {status}", "ok" if rc == 0 else "err")

    log("ORCHESTRATOR COMPLETE" if ok else "ORCHESTRATOR COMPLETED WITH FAILURES",
        "ok" if ok else "warn")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
