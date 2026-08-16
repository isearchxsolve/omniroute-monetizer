"""READ-ONLY: find how combo models are ordered for routing (weight vs array order)."""
import re

p = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\open-sse\mcp-server\server.js"
t = open(p, "r", encoding="utf-8", errors="replace").read()

# 1. context around the weight-sort function (2954423) — find its name + callers
m = re.search(r"function (\w+)\(targets, selectedExecutionKey, preserveExistingOrder", t)
if m:
    fname = m.group(1)
    print("weight-sort function name:", fname)
    for cm in re.finditer(re.escape(fname) + r"\(", t):
        s = max(0, cm.start() - 200)
        e = min(len(t), cm.end() + 250)
        seg = t[s:e].replace("\n", " ")
        print("\n--- caller @", cm.start())
        print(seg)

# 2. how combo models become targets: search for 'weight' near 'kind === "model"' or combo step normalization
for pat in [r"sortModelsByCost", r"preserveExistingOrder"]:
    print("\n\n##### pattern:", pat)
    for cm in list(re.finditer(pat, t))[:6]:
        s = max(0, cm.start() - 250)
        e = min(len(t), cm.end() + 250)
        seg = t[s:e].replace("\n", " ")
        print("\n--- @", cm.start())
        print(seg)
