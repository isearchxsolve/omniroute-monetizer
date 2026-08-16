#!/usr/bin/env python3
"""Shallow sweep: which LOCAL_OR_PUBLIC (zero-auth) providers are NOT yet
connected in OmniRoute? These need no login, no card — pure config.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

ledger = json.loads(open(os.path.join(ROOT, "state", "all_296_providers_execution_ledger.json"), encoding="utf-8").read())
provs = ledger["providers"]

zero = {k: v for k, v in provs.items() if v["status"] == "LOCAL_OR_PUBLIC"}
print(f"LOCAL_OR_PUBLIC total: {len(zero)}\n")
for k, v in zero.items():
    print(f"=== {k} ===")
    print(f"  status: {v['status']}")
    print(f"  category: {v.get('category','')}")
    print(f"  in_db_connections: {v.get('in_db_connections', 0)}")
    det = v.get("details", {})
    for dk, dv in det.items():
        s = str(dv)[:200]
        print(f"  {dk}: {s}")
    print()
