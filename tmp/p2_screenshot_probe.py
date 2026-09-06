"""Read-only: P2 clip recovery — screenshot the tab, list blob URLs and fetch the tile.

The tile <video> src is a flow.google.com/asb/ blob-mapped stream. The signed CDN URL
harvested at submit time only exists once the player requests the CDN master. Here we
screenshot (visual check, AGENTS.md rule 11) and try fetching the asb URL HEAD.
"""
import base64
import json
import sys
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    shot = pg.send("Page.captureScreenshot", {"format": "png"}, timeout=90)
    srcs = pg.evaluate(
        '(() => JSON.stringify(Array.from(document.querySelectorAll("video"))'
        '.map(v => (v.src || v.currentSrc || ""))))()', timeout=30)
srcs = json.loads(srcs)
open(r"state\diag_p2_lighthouse.png", "wb").write(base64.b64decode(shot["data"]))
print("screenshot saved: state/diag_p2_lighthouse.png")
for s in srcs:
    print("src:", s[:180])
    if s.startswith("http"):
        req = urllib.request.Request(s, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                print("  HEAD:", r.status, r.headers.get("Content-Type"),
                      r.headers.get("Content-Length"))
        except Exception as e:
            print("  HEAD error:", str(e)[:120])
