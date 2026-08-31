#!/usr/bin/env python3
"""Fleet roster DEDUP + RECONCILE across the four dedicated automation seats.

Operator directive (2026-09-01): the same chat site is declared on several profiles
(Poe on 9222/9223/9224, ChatHub on 9222/9223, ...) and run-2 drove only one profile's
live tabs. This tool makes ONE owner per chat site and aligns live tabs with it:

  1. OWNER SELECTION (evidence-first, deterministic):
       a seat holding a LIVE tab for the site keeps/gets ownership,
       then readiness verdict (session_only > signed_in_probable > visited > rest),
       then the least-loaded seat, then the lowest port.
  2. RECONCILE: a non-owner seat's duplicate tab is CLOSED only when the owner seat
     already holds its own live tab for the site (so the session stays on the owner;
     nothing is closed that would lose a signed-in surface). Owner reassignment
     follows the live evidence automatically.
  3. EXPAND: the owner seat gets a tab opened for every owned site it does not have
     live yet (the roster expansion run-2 lacked).
  4. The canonical, non-secret assignment is written to state/seat_roster_canonical.json.

Video-only sites are excluded (separate spend-gated lane). Seat attestation via
assert_safe_cdp_port; the operator's live Chrome profile is never touched.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from capture_sessions_cdp import (READINESS, assert_safe_cdp_port,  # noqa: E402
                                  host_of, reg, site_catalog, targets)

VIDEO_ONLY = ("Google Flow (labs.google)", "rtst.ai", "digen.ai")
PORTS = [9222, 9223, 9224, 9225]
VERDICT_RANK = {"session_only": 0, "signed_in_probable": 1, "visited": 2}
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="without this: report the reconciliation, change nothing")
    a = ap.parse_args()
    for p in PORTS:
        assert_safe_cdp_port(p)

    rd = json.loads(READINESS.read_text(encoding="utf-8"))
    cat = site_catalog()

    # seat -> {site name: verdict}; live tabs per seat.
    seats: dict[int, dict[str, str]] = {}
    for seat in rd.get("seats", []):
        for port in seat.get("ports") or []:
            if port in PORTS:
                # readiness rows are dicts with a "verdict" field
                seats[port] = {n: (str(v.get("verdict") or "unknown")
                                   if isinstance(v, dict) else str(v))
                               for n, v in (seat.get("sites") or {}).items()}
    live: dict[int, list] = {p: targets(p) for p in PORTS}
    live_regs: dict[int, set] = {p: {reg(host_of(t.get("url", ""))) for t in ts}
                                 for p, ts in live.items()}
    target_by_reg: dict[int, dict[str, list]] = {}
    for p, ts in live.items():
        for t in ts:
            target_by_reg.setdefault(p, {}).setdefault(
                reg(host_of(t.get("url", ""))), []).append(t)

    # All chat site names declared anywhere.
    all_sites = sorted({n for s in seats.values() for n in s} - set(VIDEO_ONLY))
    owners: dict[str, dict] = {}
    loads = {p: 0 for p in PORTS}

    for name in all_sites:
        url = cat.get(name, "")
        dom = reg(host_of(url)) if url else reg(name.replace(" ", "").lower())
        cands = []
        for p in PORTS:
            if name not in seats.get(p, {}):
                continue
            has_live = dom in live_regs.get(p, set())
            cands.append({"port": p, "verdict": seats[p][name],
                          "rank": VERDICT_RANK.get(seats[p][name], 3),
                          "has_live": has_live})
        if not cands:
            continue
        cands.sort(key=lambda c: (0 if c["has_live"] else 1, c["rank"], loads[c["port"]], c["port"]))
        owner = cands[0]
        owners[name] = {"url": url, "domain": dom, "owner": owner["port"],
                        "ownerVerdict": owner["verdict"],
                        "ownerHasLive": owner["has_live"],
                        "declaredOn": [c["port"] for c in cands],
                        "reason": ("live tab evidence" if owner["has_live"]
                                   else f"verdict {owner['verdict']} + least load")}
        loads[owner["port"]] += 1

    # --- collapse EXACT-URL duplicates within each seat (keep the first) and drop
    # about:blank strays. Same profile = same cookie jar, so closing extras loses
    # nothing. This is the video-tab accumulation the router task leaves behind when
    # it relaunches repeatedly in one day (measured 2026-09-01: 29x rtst on 9222).
    collapsed = []
    for p in PORTS:
        seen: set[str] = set()
        for t in live.get(p, []):
            url = str(t.get("url") or "")
            tid = str(t.get("id") or "")
            if url.startswith("about:blank") or url.rstrip("/") == "":
                if not a.apply:
                    collapsed.append((p, tid[:8], url[:40], "WOULD_CLOSE_BLANK"))
                    continue
                if close_target(p, tid):
                    collapsed.append((p, tid[:8], url[:40], "closed-blank"))
                continue
            key = url.rstrip("/")
            if key in seen:
                if not a.apply:
                    collapsed.append((p, tid[:8], url[:40], "WOULD_CLOSE_DUP"))
                    continue
                if close_target(p, tid):
                    collapsed.append((p, tid[:8], url[:40], "closed-dup"))
                continue
            seen.add(key)

    # --- reconcile: close non-owner duplicate tabs when the owner has its own live tab
    closed = []
    for name, o in owners.items():
        dom = o["domain"]
        if not o["ownerHasLive"]:
            continue                       # owner has no live tab: keep every live surface
        for p in PORTS:
            if p == o["owner"]:
                continue
            for t in target_by_reg.get(p, {}).get(dom, []):
                if not a.apply:
                    closed.append((name, p, t.get("id", "")[:8], "WOULD_CLOSE"))
                    continue
                if close_target(p, str(t.get("id"))):
                    closed.append((name, p, t.get("id", "")[:8], "closed"))

    # --- expand: open missing owner tabs
    opened = []
    for name, o in sorted(owners.items(), key=lambda kv: (kv[1]["owner"], kv[0])):
        if o["ownerHasLive"] or not o["url"].startswith("http"):
            continue
        if not a.apply:
            opened.append((o["owner"], name, o["url"][:50], "WOULD_OPEN"))
            continue
        if open_target(o["owner"], o["url"]):
            opened.append((o["owner"], name, o["url"][:50], "opened"))
            target_by_reg.setdefault(o["owner"], {}).setdefault(o["domain"], [])
        else:
            opened.append((o["owner"], name, o["url"][:50], "OPEN_FAILED"))

    canonical = {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "policy": "one owner per chat site; live-tab evidence first, then verdict rank, "
                  "then least-loaded seat, then lowest port; video sites excluded",
        "sites": owners,
    }
    CANON.parent.mkdir(parents=True, exist_ok=True)
    tmp = CANON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(canonical, indent=1), encoding="utf-8")
    tmp.replace(CANON)

    per_port: dict[int, int] = {p: 0 for p in PORTS}
    for o in owners.values():
        per_port[o["owner"]] += 1
    print(f"sites reconciled: {len(owners)} | owner load: "
          f"{ {p: per_port[p] for p in PORTS} }")
    print(f"tabs closed: {len(closed)} | tabs opened: {len(opened)} | "
          f"exact-URL dups/blanks collapsed: {len(collapsed)} (apply={a.apply})")
    for p, tid, url, what in collapsed[:16]:
        print(f"  coll  {what:18s} port {p} target {tid} {url}")
    for name, p, tid, what in closed[:14]:
        print(f"  close {what:12s} {name:30s} port {p} target {tid}")
    for p, name, url, what in opened[:14]:
        print(f"  open  {what:12s} {name:30s} port {p} {url}")
    print(f"wrote {CANON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
