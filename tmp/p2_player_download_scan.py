"""Open the lighthouse tile, THEN scan for download controls (they live in the player UI)."""
import json
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page
import flow_ui_client as f

SCAN = r"""
(() => {
  const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
  const hits = btns.filter(b => {
    const t = ((b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '')).toLowerCase();
    return /download|save|export/.test(t);
  }).map(b => ({
    tag: b.tagName, label: (b.getAttribute('aria-label') || b.textContent || '').trim().slice(0, 50),
    visible: b.getBoundingClientRect().width > 0
  }));
  return JSON.stringify(hits);
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    opened = pg.evaluate(f.JS_OPEN_NEWEST_TILE, timeout=60)
    print("opened:", opened)
    time.sleep(8)
    hits = json.loads(pg.evaluate(SCAN, timeout=30))
    print("download-ish controls in player:", json.dumps(hits, indent=2))
