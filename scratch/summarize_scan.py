#!/usr/bin/env python3
"""Summarize the upstream scan by verdict class, with evidence snippets."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
scan = json.loads((ROOT / "state" / "provider_upstream_scan.json").read_text(encoding="utf-8"))
res = scan["results"]

INTEREST = ["OPEN_NO_AUTH", "NEEDS_BROWSER", "LOCAL_RUNTIME", "UNKNOWN",
            "CAPTCHA_BOT_BLOCK", "PAYWALL_CREDITS", "RATE_LIMITED"]

for verdict in INTEREST:
    group = {k: v for k, v in res.items() if v.get("verdict") == verdict}
    if not group:
        continue
    print(f"\n{'='*70}\n{verdict}  ({len(group)})\n{'='*70}")
    for k in sorted(group):
        v = group[k]
        snip = (v.get("body_snippet") or v.get("note") or "").replace("\n", " ")[:110]
        print(f"  {k:24s} status={str(v.get('status')):5s} auth={str(v.get('declared_authType')):8s} {snip}")
