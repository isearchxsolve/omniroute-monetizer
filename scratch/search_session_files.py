"""Search Profile 14 binary session files for the stray 0.0.0.14 URL and
report current Chrome/CDP state."""
import os, urllib.request, json

P14 = r"d:\omniroute-chrome-profile\Profile 14"
OUT = r"d:\omniroute-monetizer\scratch\session_search.txt"
NEEDLE = b"0.0.0.14"

lines = []

# 1) CDP state
try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5) as r:
        v = json.loads(r.read())
    lines.append(f"CDP UP: {v.get('Browser')}")
    with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5) as r:
        tg = json.loads(r.read())
    for t in tg:
        lines.append(f"  target {t.get('type'):12s} {t.get('url','')[:60]!r}")
except Exception as e:
    lines.append(f"CDP DOWN: {e}")

lines.append("")

# 2) search session files
session_files = ["Current Session", "Current Tabs", "Last Session", "Last Tabs",
                 "Pinned Tabs"]
for fn in session_files:
    p = os.path.join(P14, fn)
    if not os.path.exists(p):
        lines.append(f"{fn}: (absent)")
        continue
    try:
        with open(p, "rb") as f:
            data = f.read()
        if NEEDLE in data:
            idx = data.find(NEEDLE)
            ctx = data[max(0, idx-40):idx+60]
            # show printable ascii only
            printable = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
            lines.append(f"{fn}: CONTAINS 0.0.0.14 (size={len(data)})")
            lines.append(f"    ctx: {printable}")
        else:
            lines.append(f"{fn}: no 0.0.0.14 (size={len(data)})")
    except Exception as e:
        lines.append(f"{fn}: ERROR {e}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done")
