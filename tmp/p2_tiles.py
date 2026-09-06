"""Read-only: inspect video tiles on the P2 tab (lighthouse clip watch)."""
import json
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

JS = (
    '(() => JSON.stringify(Array.from(document.querySelectorAll("video"))'
    '.map(v => ({dur: v.duration, ready: v.readyState,'
    ' src: (v.src || v.currentSrc || "").slice(0, 90)}))))()'
)

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    raw = pg.evaluate(JS, timeout=30)
print(json.dumps(json.loads(raw), indent=2))
