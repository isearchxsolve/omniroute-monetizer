"""READ-ONLY: confirm how strategy 'priority' + weights drive combo ordering."""
import re

p = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\open-sse\mcp-server\server.js"
t = open(p, "r", encoding="utf-8", errors="replace").read()

for pat in [r"resolveWeightedStepGroups", r'strategy\s*===?\s*"priority"', r'"priority"\s*===', r"hasCompositeTierRuntimeOrder"]:
    print("\n\n##### pattern:", pat)
    hits = list(re.finditer(pat, t))
    print("count:", len(hits))
    for cm in hits[:4]:
        s = max(0, cm.start() - 220)
        e = min(len(t), cm.end() + 260)
        seg = t[s:e].replace("\n", " ")
        print("\n--- @", cm.start())
        print(seg)
