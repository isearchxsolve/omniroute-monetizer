"""Read-only probe of the P2 Flow tab DOM (worklog #1640 consumer job watch)."""
import json
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page
import flow_ui_client as f

JS = r"""
(() => {
  const vids = document.querySelectorAll('video').length;
  const imgs = document.querySelectorAll('img').length;
  const gimgs = document.querySelectorAll('img[src*="googleusercontent"]').length;
  const tiles = Array.from(document.querySelectorAll('[role="button"], [role="listitem"]'))
    .filter(e => e.querySelector('img, video')).length;
  const bodyLen = document.body.innerText.length;
  return JSON.stringify({vids, imgs, gimgs, tiles, bodyLen});
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    dom = json.loads(pg.evaluate(JS, timeout=30) or "{}")
    st = json.loads(pg.evaluate(f.JS_RENDER_STATE, timeout=60) or "{}")
print("P2 DOM:", dom)
print("P2 render state:", st)
