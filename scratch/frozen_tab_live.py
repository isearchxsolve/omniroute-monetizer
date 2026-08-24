"""Prove the new FAULT_FROZEN path against real Chrome. Spends nothing: navigation only.

A discarded tab cannot be requested on demand, but a FROZEN one can -- Page.setWebLifecycleState
suspends the page's task queues, so Runtime.evaluate stops answering exactly as it did when Chrome's
memory saver discarded the tabs on 2026-08-24. That is the condition the router has to notice and
undo, so it is the condition this reproduces, on the rtst tab (a plain page: unlike Flow's, its URL
carries no project id, and its bearer lives in localStorage, which survives anything done here).

Restores the tab in a finally, whatever happens.
"""
from __future__ import annotations

import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "automation"))
import rtst_client as rt          # noqa: E402
import video_router as vr         # noqa: E402
from cdp import Page, list_targets  # noqa: E402

vp = vr.vp
FLEET = vr.load_accounts()
ACCT = next(a for a in FLEET.accounts if a.provider == "rtst")
TABS = [t for t in list_targets(ACCT.port)
        if t.get("type") == "page" and rt.TAB in (t.get("url", "") + t.get("title", "")).lower()]
TID = TABS[0].get("id")
print(f"rtst tab {TID} on port {ACCT.port}: {TABS[0].get('url')}")


def restore() -> None:
    print("\n-- restoring the tab no matter what happened above ----------------------")
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{ACCT.port}/json/activate/{TID}", timeout=20).read()
    except Exception as e:                                                   # noqa: BLE001
        print(f"  activate failed: {type(e).__name__}: {e}")
    try:
        with Page(rt.TAB, port=ACCT.port) as p:
            p.send("Page.setWebLifecycleState", {"state": "active"}, timeout=30)
            print(f"  lifecycle active, readyState = {p.evaluate('document.readyState', timeout=20)}")
    except Exception as e:                                                   # noqa: BLE001
        print(f"  lifecycle restore failed: {type(e).__name__}: {e}")
    FLEET.probe(ACCT)
    print(f"  final state: ready={ACCT.ready} fault={ACCT.fault} credits={ACCT.credits} "
          f"({ACCT.reason})")


try:
    # Chrome refuses to freeze the tab the user is looking at: the lifecycle state only applies to a
    # HIDDEN page. So bring some other tab to the front first -- the freeze is what has to be real
    # here, not which tab happens to be visible in a window nobody is watching.
    others = [t for t in list_targets(ACCT.port)
              if t.get("type") == "page" and t.get("id") != TID]
    if others:
        urllib.request.urlopen(
            f"http://127.0.0.1:{ACCT.port}/json/activate/{others[0]['id']}", timeout=20).read()
        print(f"foregrounded {others[0].get('url', '')[:60]} so the rtst tab is hidden")
        time.sleep(2)

    with Page(rt.TAB, port=ACCT.port) as p:
        print(f"before: readyState = {p.evaluate('document.readyState', timeout=20)}")
        print(f"        visibility = {p.evaluate('document.visibilityState', timeout=20)}")
        p.send("Page.setWebLifecycleState", {"state": "frozen"}, timeout=30)
        print("sent Page.setWebLifecycleState frozen")

    print("\n-- does the tab still run JS? -------------------------------------------")
    # MEASURED: an evaluate fired immediately after the freeze command usually still answers -- the
    # task queues drain what is already queued, and a fresh CDP attach nudges the page. Wait for the
    # freeze to actually bite before concluding anything; the fleet probe below is the real verdict.
    time.sleep(5)
    t0 = time.time()
    try:
        with Page(rt.TAB, port=ACCT.port) as p:
            print(f"  it does: readyState = {p.evaluate('document.readyState', timeout=20)} "
                  f"-- an attach can thaw it; the probe below is what counts")
    except Exception as e:                                                   # noqa: BLE001
        print(f"  no: evaluate failed after {time.time() - t0:.1f}s: {type(e).__name__}: "
              f"{str(e)[:80]}")
        print(f"  vp.is_frozen() says: {vp.is_frozen(e)}")

    print("\n-- what does the fleet make of it? --------------------------------------")
    print(f"  /json/list still lists {len([t for t in list_targets(ACCT.port) if t.get('type') == 'page'])} "
          f"page target(s) -- the port and the tab both still look healthy")
    t0 = time.time()
    FLEET.probe(ACCT)
    print(f"  probe took {time.time() - t0:.0f}s: ready={ACCT.ready} fault={ACCT.fault!r}")
    print(f"  reason: {ACCT.reason}")
    print(f"  heal-able: {ACCT.fault in vp.HEALABLE}")

    print("\n-- wake --dry-run would do ----------------------------------------------")
    for r in FLEET.heal(dry_run=True):
        print(f"  {r['action']}: {r['detail']}")

    print("\n-- and for real (navigation only, 0 credits) ---------------------------")
    for r in FLEET.heal():
        print(f"  {r['action']}: ok={r['ok']}: {r['detail']}")
    print(f"  heal counters: {FLEET.heal_stats}")
    print(f"  account now: ready={ACCT.ready} fault={ACCT.fault} credits={ACCT.credits}")
finally:
    restore()
