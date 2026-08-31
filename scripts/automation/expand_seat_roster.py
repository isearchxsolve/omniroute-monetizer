#!/usr/bin/env python3
"""Expand one dedicated automation seat's chat roster: open a tab for every declared
chat site of that seat (state/seat_readiness.json) that has no live tab on its
registrable domain yet. Idempotent; skips video-only sites (separate spend-gated lane).

Seat attestation: assert_safe_cdp_port refuses non-automation CDP endpoints before any
socket is opened. Never touches the operator's live Chrome profile.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from capture_sessions_cdp import (SECRETS, assert_safe_cdp_port, host_of,  # noqa: E402
                                  reg, site_catalog, targets)
from tab_graduation_sweep import READINESS  # noqa: E402

VIDEO_ONLY = ("Google Flow (labs.google)", "rtst.ai", "digen.ai")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    assert_safe_cdp_port(a.port)

    rd = json.loads(READINESS.read_text(encoding="utf-8"))
    seat = next((s for s in rd.get("seats", []) if a.port in (s.get("ports") or [])), None)
    if not seat:
        raise SystemExit(f"no readiness seat declares port {a.port}")
    cat = site_catalog()

    live = targets(a.port)
    live_regs = {reg(host_of(t.get("url", ""))) for t in live}
    have, opened, skipped = [], [], []
    for name in sorted(seat.get("sites") or {}):
        if name in VIDEO_ONLY:
            continue
        url = cat.get(name, "")
        if not url.startswith("http"):
            skipped.append((name, "no catalog url"))
            continue
        if reg(host_of(url)) in live_regs:
            have.append(name)
            continue
        if a.dry_run:
            opened.append((name, url))
            continue
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{a.port}/json/new?{url}", method="PUT")
        with urllib.request.urlopen(req, timeout=15) as r:
            new = json.loads(r.read().decode("utf-8", "replace"))
        opened.append((name, (new.get("url") or url)[:60]))
        live_regs.add(reg(host_of(url)))
        print(f"  opened {name:32s} {url[:60]}")
    print(f"port {a.port}: live_before={len(live)} already_open={len(have)} "
          f"opened={len(opened)} skipped={len(skipped)}")
    for name, why in skipped:
        print(f"  skip  {name:32s} {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
