"""Decisive diagnostic: what PRECEDES each [AUTO] auto/zai warning burst in app.log?
The warnings are emitted DURING catalog rebuilds, so the lines immediately before
the first warning of each burst should reveal the rebuild TRIGGER (request path,
background job, DB write, version bump)."""
import json, os, re

LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

# Read all lines (17.5MB is fine in memory)
with open(LOG, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

print("total lines:", len(lines))

# Find indices of auto/zai warnings
warn_idx = [i for i, ln in enumerate(lines) if "auto/zai matched no connected models" in ln]
print("auto/zai warnings:", len(warn_idx))

def fmt(ln):
    """Compact one-line rendering of a log line."""
    ln = ln.rstrip("\n")
    try:
        o = json.loads(ln)
        ts = o.get("timestamp") or o.get("time") or o.get("ts") or ""
        lvl = o.get("level", "")
        msg = o.get("message") or o.get("msg") or ""
        extra = {k: v for k, v in o.items() if k not in ("timestamp", "time", "ts", "level", "message", "msg")}
        s = f"{ts} [{lvl}] {msg}"
        if extra:
            s += " | " + json.dumps(extra)[:220]
        return s
    except Exception:
        return ln[:300]

# Group warnings into bursts (warnings <3s apart by line proximity = same burst)
bursts = []
cur = [warn_idx[0]]
for i in warn_idx[1:]:
    if i - cur[-1] <= 60:  # line-proximity heuristic for same burst
        cur.append(i)
    else:
        bursts.append(cur)
        cur = [i]
bursts.append(cur)
print("bursts:", len(bursts))

# For the last 6 bursts, print 12 lines BEFORE the first warning of the burst
for b in bursts[-6:]:
    start = b[0]
    print("\n" + "=" * 100)
    print(f"BURST of {len(b)} warnings, first at line {start}")
    print("-" * 100)
    for i in range(max(0, start - 12), min(len(lines), b[-1] + 2)):
        marker = ">>>" if i in b else "   "
        print(f"{marker}[{i}] {fmt(lines[i])}")
