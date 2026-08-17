#!/usr/bin/env python3
"""Inspect the extracted provider base URLs and classify their shape."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
bu = json.loads((ROOT / "state" / "provider_baseurls.json").read_text(encoding="utf-8"))
led = json.loads((ROOT / "state" / "all_296_providers_execution_ledger.json").read_text(encoding="utf-8"))["providers"]

ext = {k: v for k, v in led.items() if (v.get("status") if isinstance(v, dict) else v) == "EXTERNAL_ACCOUNT_REQUIRED"}
have = {k: bu[k] for k in ext if k in bu}

print(f"unconfigured with baseUrl: {len(have)}\n")
for k in sorted(have):
    v = have[k]
    print(f"{k:24s} auth={str(v.get('authType')):10s} {v['baseUrl']}")
