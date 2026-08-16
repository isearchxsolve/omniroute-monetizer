"""READ-ONLY: extract sort-ordering logic context from OmniRoute runtime source."""
import re

p = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\open-sse\mcp-server\server.js"
t = open(p, "r", encoding="utf-8", errors="replace").read()
pats = [r"b\.priority - a\.priority", r"a\.priority - b\.priority", r"b\.weight - a\.weight"]
for pat in pats:
    for m in re.finditer(pat, t):
        s = max(0, m.start() - 300)
        e = min(len(t), m.end() + 150)
        seg = t[s:e].replace("\n", " ")
        print("=====", pat, "@", m.start())
        print(seg)
        print()
