"""Read-only: count current session clips on P2 (:9226) — grid tile + sidebar Videos count."""
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

JS = r"""
(() => {
  const grids = Array.from(document.querySelectorAll('grid-view, [class*="grid"]'));
  const allVideos = document.querySelectorAll('video').length;
  const mediaCells = Array.from(document.querySelectorAll('mat-mdc-tooltip-trigger, [class*="media"]')).length;
  const canvas = document.querySelectorAll('canvas').length;
  return JSON.stringify({grids: grids.length, allVideos, mediaCells, canvas});
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    raw = pg.evaluate(JS, timeout=30)
import json
print(json.dumps(json.loads(raw), indent=2))
