"""scratch_grok_conns.py — enumerate ALL grok tabs/targets across all seat Chromes."""
import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import targets

for port in (9222, 9223, 9224, 9225):
    try:
        ts = targets(port)
    except Exception as e:
        print(f"port {port}: {type(e).__name__} {e}")
        continue
    grok = [t for t in ts if "grok" in (t.get("url") or "").lower()]
    print(f"\n=== port {port}: {len(ts)} targets, {len(grok)} grok ===")
    for t in grok:
        print(f"  [{t.get('type')}] {t.get('url','')[:80]}")
    # also list service workers / background pages generally
    for t in ts:
        if t.get("type") in ("service_worker", "background_page"):
            print(f"  (bg) [{t.get('type')}] {t.get('url','')[:80]}")
