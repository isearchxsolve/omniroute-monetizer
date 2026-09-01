#!/usr/bin/env python3
"""Fleet reconcile v2 - CONSTANT-N MIRROR policy (operator directive 2026-09-01).

n = |union of ALL declared sites across the fleet (chat + video)|.
Every profile holds EXACTLY n tabs: one per declared site, same set everywhere.
Ownership is symmetric: profiles are mirrors, not partitions.

Deterministic: a second run with no site changes opens nothing and closes nothing.
Verification is by direct /json/list re-listing, never by the tool's own intent.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from capture_sessions_cdp import (READINESS, assert_safe_cdp_port, host_of,  # noqa: E402
                                  reg, site_catalog, targets)

PORTS = [9222, 9223, 9224, 9225]
CANON = ROOT / "state" / "seat_roster_canonical.json"


def close_target(port: int, target_id: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{target_id}",
                                    timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def open_target(port: int, url: str) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}",
                                     method="PUT")
        with urllib.request.urlopen(req, timeout=15) as r:
            return bool(json.loads(r.read().decode("utf-8", "replace")).get("id"))
    except Exception:
        return False


def match_sites(tabs, union_regs, reg_counts):
    """Map site name -> live tab. Host-exact first; unique-registrable-domain second
    (tolerates site redirects like baichuan -> yi.baichuan-ai). Shared registrable
    domains (google.com: labs.google + gemini) require host equality."""
    site_tab: dict[str, dict] = {}
    used: set[str] = set()
    for name, (host, r) in union_regs.items():
        for t in tabs:
            tid = str(t.get("id"))
            if tid in used:
                continue
            if host_of(t.get("url") or "") == host:
                site_tab[name] = t
                used.add(tid)
                break
    for name, (host, r) in union_regs.items():
        if name in site_tab or reg_counts[r] != 1:
            continue
        for t in tabs:
            tid = str(t.get("id"))
            if tid in used:
                continue
            if reg(host_of(t.get("url") or "")) == r:
                site_tab[name] = t
                used.add(tid)
                break
    return site_tab, used


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", type=int, action="append",
                    help="work ONLY this port (one-profile-at-a-time mode); repeatable")
    a = ap.parse_args()
    ports = a.only or PORTS
    for p in ports:
        assert_safe_cdp_port(p)

    rd = json.loads(READINESS.read_text(encoding="utf-8"))
    cat = site_catalog()
    union: dict[str, str] = {}
    for seat in rd.get("seats", []):
        for name in (seat.get("sites") or {}):
            if name not in union and cat.get(name, "").startswith("http"):
                union[name] = cat[name]
    # chatx.ai: hard-403 from this host (Cloudflare) and the opened tab redirects to
    # chatgpt.com (ChatX's own anonymous-visitor redirect). The site is un-reachable
    # as its own tab; its earlier artifact is turnstile-wall-classified (#1439). Keeping
    # it in the union would wedge the mirror into a permanently-missing tab, so it is
    # parked with a recorded reason instead. Re-include when the site stops 403ing.
    PARKED = {"ChatX": "site 403s from this host; opens redirect to chatgpt.com; "
                       "artifact already WALL-classified (turnstile)"}
    for name in PARKED:
        union.pop(name, None)
    n = len(union)
    union_regs = {name: (host_of(url), reg(host_of(url))) for name, url in union.items()}
    reg_counts = Counter(r for _, r in union_regs.values())

    report = {"policy": "CONSTANT_N_MIRROR", "n": n, "ports": {}}
    totals = {"closed_dup": 0, "closed_stray": 0, "closed_blank": 0, "opened": 0}

    for port in ports:
        try:
            tabs = [t for t in targets(port) if t.get("type") == "page"]
        except Exception as e:
            report["ports"][port] = {"error": type(e).__name__}
            print(f"port {port}: UNREACHABLE ({type(e).__name__})")
            continue
        site_tab, used = match_sites(tabs, union_regs, reg_counts)

        # close unmatched tabs: same-site extras, non-union strays, blanks
        for t in tabs:
            tid = str(t.get("id"))
            if tid in used:
                continue
            url = t.get("url") or ""
            kind = ("blank" if url.startswith("about:blank") or url == ""
                    else "stray")
            if a.apply:
                if close_target(port, tid):
                    totals[f"closed_{kind}"] += 1
            else:
                totals[f"closed_{kind}"] += 0

        # open missing union sites
        missing = [name for name in union if name not in site_tab]
        for name in sorted(missing):
            if a.apply:
                if open_target(port, union[name]):
                    totals["opened"] += 1
                time.sleep(0.4)
            else:
                totals["opened"] += 0

        # re-list and verify
        time.sleep(2.5 if a.apply else 0)
        tabs2 = [t for t in targets(port) if t.get("type") == "page"]
        site_tab2, used2 = match_sites(tabs2, union_regs, reg_counts)
        extras = len(tabs2) - len(used2)
        report["ports"][port] = {"matchedSites": len(site_tab2), "tabs": len(tabs2),
                                 "unmatchedTabs": extras}
        ok = len(site_tab2) == n and extras == 0
        print(f"port {port}: matched {len(site_tab2)}/{n} union sites | "
              f"{len(tabs2)} tabs | unmatched {extras} | {'OK' if ok else 'MISALIGNED'}")

    report["totals"] = totals
    report["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = CANON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=1), encoding="utf-8")
    tmp.replace(CANON)
    print(f"n={n} | totals={totals} | apply={a.apply}")
    print(f"wrote {CANON.relative_to(ROOT)}")
    aligned = all(isinstance(v, dict) and v.get("matchedSites") == n and v.get("unmatchedTabs") == 0
                  for v in report["ports"].values())
    print("FLEET ALIGNED" if aligned else "FLEET NOT ALIGNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
