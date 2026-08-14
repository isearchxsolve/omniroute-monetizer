#!/usr/bin/env python3
"""
CLI/orchestration wrapper for the generalized provider browser engine.

This is deliberately narrow:
- choose a provider
- perform DOM discovery
- optionally perform a safe re-auth probe
- produce sanitized artifacts
- never touch Windows service control
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

from provider_browser_engine import ProviderBrowserEngine

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", required=True)
    p.add_argument("--artifact-dir", default="state/browser_automation")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--reauth-probe", action="store_true")
    args = p.parse_args()

    engine = ProviderBrowserEngine(
        artifact_dir=Path(args.artifact_dir),
        headless=args.headless,
    )

    result = (
        engine.safe_reauth_probe(args.provider)
        if args.reauth_probe
        else engine.discover(args.provider)
    )

    print(json.dumps(result.sanitized(), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
