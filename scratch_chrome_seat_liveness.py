"""Cross-reference all 33 Chrome-backed seats against LIVE tabs on the 4 seat Chromes.

Read-only: only GET /json/list (list_targets) — no typing, no generation, no spend.
For each Chrome-backed seat, compute its tab substring exactly the way its client does:
  - chat: ChromeReplayClient -> inline chrome.tab, else CHROME_CLIENTS.get(host, host)
  - video: ChromeVideoClient -> VIDEO_HOSTS[host]['tab'], else inline chrome.tab
Then match against live page targets on ports 9222-9225.
"""
import sys, pathlib, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))

from session_pool import SessionPool
from chrome_replay_client import ChromeReplayClient, CHROME_CLIENTS, TAB_EXCLUDES
from chrome_video_client import ChromeVideoClient, VIDEO_HOSTS, CDP_PORTS
from cdp import list_targets

# gather live page targets per port
targets = {}
for port in CDP_PORTS:
    try:
        ts = [t for t in list_targets(port) if t.get("type") == "page"]
        targets[port] = ts
    except Exception as e:
        targets[port] = None
        print("PORT %d: list_targets FAILED: %s" % (port, e))

for port, ts in targets.items():
    if ts is not None:
        print("PORT %d: %d live page targets" % (port, len(ts)))
print()

p = SessionPool()
chrome_seats = [s for s in p.sessions
                if s.client_cls in (ChromeReplayClient, ChromeVideoClient)]

def tab_substr_for(s):
    raw = __import__("json").loads(s.path.read_text(encoding="utf-8-sig"))
    decl = raw.get("chrome")
    if isinstance(decl, dict) and decl.get("tab"):
        return str(decl["tab"]), "inline"
    if isinstance(decl, str) and decl:
        return decl, "inline"
    if s.client_cls is ChromeVideoClient:
        spec = VIDEO_HOSTS.get(s.host)
        if spec:
            return spec["tab"], "VIDEO_HOSTS"
        return s.host, "host-fallback"
    return CHROME_CLIENTS.get(s.host, s.host), "CHROME_CLIENTS"

live, notab = [], []
for s in sorted(chrome_seats, key=lambda x: (x.modality, x.key)):
    substr, src = tab_substr_for(s)
    excludes = TAB_EXCLUDES.get(s.host, [])
    hits = []
    for port, ts in targets.items():
        if ts is None:
            continue
        for t in ts:
            u = (t.get("url") or "")
            if substr.lower() in u.lower() and not any(x in u for x in excludes):
                hits.append(port)
                break
    if hits:
        live.append((s.key, s.modality, substr, sorted(set(hits))))
    else:
        notab.append((s.key, s.modality, substr, src))

print("=== CHROME-BACKED SEATS WITH LIVE TABS: %d ===" % len(live))
for key, mod, substr, ports in live:
    print("  LIVE    %-34s %-6s tab=%r ports=%s" % (key, mod, substr, ports))
print()
print("=== CHROME-BACKED SEATS WITH NO LIVE TAB: %d ===" % len(notab))
for key, mod, substr, src in notab:
    print("  NO_TAB  %-34s %-6s tab=%r (%s)" % (key, mod, substr, src))
print()
print("SUMMARY: %d/%d chrome-backed seats have live tabs" % (len(live), len(chrome_seats)))
