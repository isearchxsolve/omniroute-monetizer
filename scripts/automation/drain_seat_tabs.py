#!/usr/bin/env python3
"""Drain one seat: close every page tab after its e2e window. The seat's Chrome stays
up; the video-router task restores registered video destinations on its next tick.
Session-only logins die with the window -- Google SSO re-auth is one click per site
(cheap, as proven on chathub/monica). This is the resource-relief half of the
one-profile-at-a-time e2e cycle (operator directive 2026-09-01)."""
from __future__ import annotations

import argparse
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture_sessions_cdp import assert_safe_cdp_port, targets  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    assert_safe_cdp_port(a.port)
    ts = [t for t in targets(a.port) if t.get("type") == "page"]
    print(f"port {a.port}: draining {len(ts)} tabs")
    import urllib.request
    closed = 0
    for t in ts:
        tid = str(t.get("id"))
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/close/{tid}",
                                        timeout=10) as r:
                if r.status == 200:
                    closed += 1
        except Exception as e:
            print(f"  close fail {tid[:8]} {type(e).__name__}")
    print(f"closed {closed}/{len(ts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
