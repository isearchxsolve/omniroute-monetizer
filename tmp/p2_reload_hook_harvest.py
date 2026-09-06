"""Reload the P2 tab and wait longer for the media grid to populate, then click newest tile.

The previous nav (from batchexecute harvest) left the grid unmounted. Give the SPA a
full reload + generous settle, verify tiles>0, then open the player and hook fetch.
"""
import json
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page
import flow_ui_client as f

HOOK = r"""
(() => {
  window.__hits = [];
  const of = window.fetch;
  window.fetch = function(...a) {
    try { const u = String((a[0] && a[0].url) || a[0]);
      if (/flow-content\.google\/(video|image)\//.test(u)) window.__hits.push(u); } catch (e) {}
    return of.apply(this, a);
  };
  return 'HOOKED';
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    pg.send("Page.navigate",
            {"url": "https://flow.google.com/project/1d8d0d9f-ba25-450d-ad0b-27ef39c619e9"},
            timeout=60)
    tiles = 0
    for i in range(20):
        time.sleep(6)
        tiles = pg.evaluate('(() => document.querySelectorAll("video").length)()', timeout=30)
        print(f"[{i}] tiles={tiles}")
        if tiles:
            break
    if not tiles:
        print("GRID_NEVER_MOUNTED")
        sys.exit(1)
    print("hook:", pg.evaluate(HOOK, timeout=30))
    opened = pg.evaluate(f.JS_OPEN_NEWEST_TILE, timeout=60)
    print("opened:", opened)
    for i in range(8):
        time.sleep(5)
        hits = json.loads(pg.evaluate("(() => JSON.stringify(window.__hits))()", timeout=30))
        if hits:
            print(f"[{i}] fetch hits:")
            for h in hits:
                print("  ", h[:200])
            break
    else:
        print("no fetch hits after player open; hits=", hits)
