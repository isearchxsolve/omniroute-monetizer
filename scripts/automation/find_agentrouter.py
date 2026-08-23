"""Find agentrouter in server chunks.
"""
from __future__ import annotations
import pathlib
import re

for p in pathlib.Path(".").rglob("*agentrouter*"):
    print(p)

# Also check dist or Next.js chunks if any
for p in pathlib.Path(".").rglob("*.js"):
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "agentrouter" in txt:
            print("Found in:", p)
            for m in re.finditer(r"agentrouter[^\n]{0,200}", txt):
                print("  ", m.group(0)[:120])
    except Exception:
        pass
