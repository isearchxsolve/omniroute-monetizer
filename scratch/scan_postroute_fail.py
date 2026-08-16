"""Full context around the post-restart openrouter failures (13:14-13:16 UTC)."""
import json

LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

# find indices of the 13:14:58 and 13:15:39 unavailable lines
targets = []
for i, l in enumerate(lines):
    if "accounts unavailable" in l and ("13:14:58" in l or "13:15:39" in l):
        targets.append(i)

print("target indices:", targets)
for idx in targets:
    print(f"\n=== context around line {idx} ===")
    for i in range(max(0, idx - 8), min(len(lines), idx + 6)):
        l = lines[i]
        try:
            j = json.loads(l)
            t = j.get("time", "")
            lvl = j.get("level", "")
            msg = (j.get("msg") or "")[:260]
            extra = {k: v for k, v in j.items() if k not in ("time", "level", "msg", "pid", "hostname")}
            ex = json.dumps(extra)[:200] if extra else ""
            print(f"{i:6d} [{t}] lvl={lvl} {msg} {ex}")
        except Exception:
            print(f"{i:6d} RAW: {l[:260]}")
