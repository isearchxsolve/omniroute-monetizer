"""Recovery attempt: open newest tile (videoTiles=2 now) and harvest CDN via perf entries.

After a fresh reload, opening the player may mount the CDN URL in performance entries.
"""
import json
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page
import flow_ui_client as f

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    opened = pg.evaluate(f.JS_OPEN_NEWEST_TILE, timeout=60)
    print("opened:", opened)
    for i in range(6):
        time.sleep(5)
        cdn = pg.evaluate(f.JS_CDN_ALL, timeout=30)
        urls = json.loads(cdn or "[]")
        print(f"[{i}] cdn urls: {len(urls)}")
        if urls:
            for u in urls:
                print(" ", u[:200])
            break
