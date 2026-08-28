"""Enumerate EVERY seat in the pool and classify its execution tier.

Tiers (per TECHNOLOGY_TRANSFER §23 + session_pool._client_for):
  STATELESS-REPLAY : file-backed recorded bytes replayed over pure HTTP
                     (UniversalSessionClient / VideoUniversalSessionClient / ChatXReplayClient /
                      legacy CLIENTS replay). NO Chrome needed.
  API-CREDENTIAL   : bearer-token seat with a documented contract (RtstApiClient / FlowApiClient /
                     YouComApiClient). NO Chrome needed.
  CHROME-BACKED    : ChromeReplayClient / ChromeVideoClient — the live signed-in tab IS the
                     credential; NEEDS a live seat Chrome (9222-9225).

This is the honest answer to "did ALL tabs graduate to stateless chrome-independent?".
Read-only: no spend, no Chrome driven.
"""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))

from session_pool import SessionPool
from chrome_replay_client import ChromeReplayClient
from chrome_video_client import ChromeVideoClient

API_CLIENT_NAMES = {"RtstApiClient", "FlowApiClient", "YouComApiClient"}

p = SessionPool()
rows = []
for s in sorted(p.sessions, key=lambda x: (x.modality, x.key)):
    cls = s.client_cls.__name__ if s.client_cls else "None"
    if cls in API_CLIENT_NAMES:
        tier = "API"
    elif s.client_cls in (ChromeReplayClient, ChromeVideoClient) or cls in ("ChromeReplayClient", "ChromeVideoClient"):
        tier = "CHROME"
    elif s.has_recording:
        tier = "REPLAY"
    elif s.has_api:
        tier = "API"
    else:
        tier = "?"
    rows.append((s.key, s.modality, tier, cls, s.dispatchable, s.has_recording, s.has_api, s.has_chrome or s.has_video_chrome))

# summary
from collections import Counter
by_mod = {}
for key, mod, tier, cls, disp, rec, api, chr_ in rows:
    by_mod.setdefault(mod, Counter())[tier] += 1

print("%-36s %-6s %-8s %-26s %-5s rec api chr" % ("seat", "modal", "tier", "client", "disp"))
for key, mod, tier, cls, disp, rec, api, chr_ in rows:
    print("%-36s %-6s %-8s %-26s %-5s %-3s %-3s %-3s" % (
        key, mod, tier, cls, str(disp),
        "Y" if rec else "-", "Y" if api else "-", "Y" if chr_ else "-"))

print()
for mod, cnt in sorted(by_mod.items()):
    total = sum(cnt.values())
    stateless = cnt.get("REPLAY", 0) + cnt.get("API", 0)
    chrome = cnt.get("CHROME", 0)
    print("%-6s: %d seats | stateless(REPLAY+API)=%d | CHROME-BACKED=%d | unknown=%d" % (
        mod, total, stateless, chrome, cnt.get("?", 0)))

tot = len(rows)
tot_stateless = sum(1 for r in rows if r[2] in ("REPLAY", "API"))
tot_chrome = sum(1 for r in rows if r[2] == "CHROME")
print()
print("TOTAL: %d seats | stateless=%d | chrome-backed=%d" % (tot, tot_stateless, tot_chrome))
if tot_chrome > 0:
    print("ANSWER: NOT ALL seats are stateless chrome-independent. %d still NEED a live seat Chrome." % tot_chrome)
else:
    print("ANSWER: ALL seats are stateless chrome-independent.")
