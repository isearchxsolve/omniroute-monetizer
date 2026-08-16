"""Scan OmniRoute app.log tail for errors + find the restart boundary."""
import json
import re

LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

print("total lines:", len(lines))

# find startup markers to locate restart boundaries
starts = [i for i, l in enumerate(lines) if "STARTUP" in l and ("bootstrap" in l.lower() or "Ready in" in l or "Embedded services" in l)]
print("startup marker lines (last 5):", starts[-5:])

# scan last 2000 lines for errors
tail = lines[-2000:]
err_lines = []
for l in tail:
    if '"level":50' in l or '"level":60' in l or '"err"' in l or '"error"' in l.lower():
        err_lines.append(l)

print(f"error-ish lines in last 2000: {len(err_lines)}")
print("--- last 20 error lines (truncated) ---")
for e in err_lines[-20:]:
    try:
        j = json.loads(e)
        msg = j.get("msg") or j.get("message") or ""
        lvl = j.get("level")
        t = j.get("time") or j.get("timestamp") or ""
        err = j.get("err")
        if isinstance(err, dict):
            err = err.get("message", "")
        print(f"[{t}] lvl={lvl} {msg[:200]} | err={str(err)[:200]}")
    except Exception:
        print(e[:300])
