"""scratch_hard_tabs.py — survey live signed-in tabs for the hard providers (doctrine 3a targets)."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import targets

HARD = ["copilot.microsoft.com", "www.meta.ai", "claude.ai", "v0.app", "grok.com"]
for port in (9222, 9223, 9224, 9225):
    try:
        ts = targets(port)
    except Exception as e:
        print(f"port {port}: {type(e).__name__} {e}")
        continue
    print(f"\n=== port {port}: {len(ts)} targets ===")
    for h in HARD:
        hits = [t for t in ts if h in (t.get("url") or "").lower()]
        for t in hits:
            print(f"  {h:24s} [{t.get('type')}] {t.get('url','')[:90]}")
