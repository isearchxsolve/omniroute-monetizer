"""Catalog all background scheduler startup banners in the dist bundle."""
import os
import re

CHUNKS = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"
files = [os.path.join(CHUNKS, f) for f in os.listdir(CHUNKS) if f.endswith(".js") and not f.startswith("node_modules")]

seen = set()
for f in files:
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    # find banner-like strings near setInterval/setTimeout schedulers
    for m in re.finditer(r"[`\"'](\[[A-Za-z]+\][^`\"']{0,80}(?:Starting|started|scheduler|sweep|tick every|background)[^`\"']{0,60})[`\"']", s, re.IGNORECASE):
        txt = m.group(1)
        if txt not in seen:
            seen.add(txt)
            has_timer = ("setInterval" in s or "setTimeout" in s)
            print(f"{txt}   [{os.path.basename(f)}]")

print(f"\ntotal unique banners: {len(seen)}")
