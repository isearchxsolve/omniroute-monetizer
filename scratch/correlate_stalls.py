"""Correlate app.log component activity with observed stall windows.

Stall windows (local = UTC+6):
  S1: 04:20:49-04:21:24 local = 22:20:49-22:21:24 UTC  (wait, recompute below)
Actual stall windows from observer (local times, UTC = local - 6h):
  S1: blocked 04:20:49->04:21:24 local
  S2: blocked 04:22:20->04:23:01 local
  S3: blocked 04:24:01->04:24:45 local
Local here is UTC+6? Timestamps in log are UTC (22:xx) while local clock shows 04:xx.
So UTC = local - 6h. Stall windows in UTC:
  S1: 22:20:49-22:21:24
  S2: 22:22:20-22:23:01
  S3: 22:24:01-22:24:45
"""
import json
import re
from collections import Counter

LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

# Stall windows. Local clock is UTC+5:30 (log 22:39Z == local 04:09).
# Convert observed LOCAL stall times to UTC by subtracting 5:30.
# Observer stalls (local start->end): 04:20:49->04:21:24, 04:22:19->04:23:01, 04:24:01->04:24:45
# probe_continuous stalls (local start): 04:16:21, 04:18:03, 04:19:45, 04:21:22, 04:22:59
windows = [
    ("O1", "2026-08-15T22:50:44", "2026-08-15T22:51:30"),
    ("O2", "2026-08-15T22:52:14", "2026-08-15T22:53:06"),
    ("O3", "2026-08-15T22:53:56", "2026-08-15T22:54:50"),
    ("P1", "2026-08-15T22:46:16", "2026-08-15T22:47:03"),
    ("P2", "2026-08-15T22:47:58", "2026-08-15T22:48:45"),
    ("P3", "2026-08-15T22:49:40", "2026-08-15T22:50:27"),
    ("P4", "2026-08-15T22:51:17", "2026-08-15T22:52:04"),
]

lines = open(LOG, encoding="utf-8", errors="replace").readlines()
print(f"total log lines: {len(lines)}")

parsed = []
for ln in lines:
    try:
        o = json.loads(ln)
        parsed.append((o.get("timestamp", ""), o.get("component", "?"), o.get("message", "")[:100]))
    except Exception:
        pass
print(f"parsed: {len(parsed)}")

for name, lo, hi in windows:
    print(f"\n=== {name}: {lo} .. {hi} ===")
    comp = Counter()
    samples = []
    for ts, c, msg in parsed:
        if lo <= ts <= hi:
            comp[c] += 1
            if len(samples) < 8:
                samples.append((ts, c, msg))
    print(f"  lines in window: {sum(comp.values())}  components: {dict(comp)}")
    for ts, c, msg in samples:
        print(f"    {ts} [{c}] {msg}")
