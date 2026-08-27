# -*- coding: utf-8 -*-
"""Coverage matrix: every open tab in the automation browser (port 9222) vs.
(a) dispatchable pool seats, (b) CHROME_CLIENTS bridge entries.

Reports UNCOVERED tabs honestly — a tab with no seat and no bridge entry is
real supply sitting unused (the exact failure the Adapter Thesis exists to fix).
"""
import json, sys, pathlib, urllib.request
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from session_pool import SessionPool
from chrome_replay_client import CHROME_CLIENTS

# 1. open tabs
d = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5).read())
tabs = sorted({urlparse(t.get("url", "")).netloc.lower().replace("www.", "")
               for t in d if t.get("type") == "page" and t.get("url", "").startswith("http")})

# 2. pool seats
pool = SessionPool()
seat_hosts = {}
for s in pool.sessions:
    h = s.host.lower().replace("www.", "")
    seat_hosts.setdefault(h, []).append(s)

# bridge tab substrings (values of CHROME_CLIENTS)
bridge_substrs = set(v.lower() for v in CHROME_CLIENTS.values())

def covered(tab):
    reasons = []
    # seat match: seat host contained in tab netloc or vice versa
    for h, seats in seat_hosts.items():
        if h in tab or tab in h or h.split(".")[0] == tab.split(".")[0] and len(h.split(".")[0]) > 3:
            for s in seats:
                if s.dispatchable:
                    reasons.append("SEAT:%s(%s,%s)" % (s.host, s.modality,
                                   s.client_cls.__name__ if s.client_cls else "?"))
    # bridge match
    for sub in bridge_substrs:
        if sub in tab:
            reasons.append("BRIDGE:" + sub)
    return reasons

print("open tab hosts: %d\n" % len(tabs))
covered_n, uncovered = 0, []
for tab in tabs:
    r = covered(tab)
    if r:
        covered_n += 1
        print("COVERED   %-28s %s" % (tab, " | ".join(r)))
    else:
        uncovered.append(tab)
        print("UNCOVERED %-28s (no seat, no bridge entry)" % tab)

print("\n=== SUMMARY ===")
print("tabs: %d | covered: %d | uncovered: %d" % (len(tabs), covered_n, len(uncovered)))
print("uncovered list:", uncovered)
