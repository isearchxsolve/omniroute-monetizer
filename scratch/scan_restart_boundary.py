"""Show log lines around the restart boundary to find what killed the previous instance."""
import json

LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

# last startup markers: 106257, 106272, 106273 (0-indexed)
# show 40 lines before the boundary and 10 after
boundary = 106257
print(f"=== lines {boundary-40} .. {boundary+10} ===")
for i in range(max(0, boundary - 40), min(len(lines), boundary + 10)):
    l = lines[i]
    try:
        j = json.loads(l)
        t = j.get("time", "")
        lvl = j.get("level", "")
        msg = (j.get("msg") or j.get("message") or "")[:180]
        print(f"{i:6d} [{t}] lvl={lvl} {msg}")
    except Exception:
        print(f"{i:6d} RAW: {l[:180]}")
