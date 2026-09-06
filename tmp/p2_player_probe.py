"""Read-only: click the newest tile on :9226, watch network for flow-content video fetches.

The player streams via the media endpoint; performance resource entries may not include
media segment fetches. This watches via DOM <video> src + a manual HEAD on the tile's
media URL pattern, and also checks the session-level media list by re-reading innerText
after opening the player.
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
    time.sleep(12)
    full = pg.evaluate("(() => document.body.innerText)()", timeout=30)
    st = pg.evaluate(f.JS_RENDER_STATE, timeout=60)
    srcs = pg.evaluate(
        '(() => JSON.stringify(Array.from(document.querySelectorAll("video"))'
        '.map(v => (v.src || v.currentSrc || "").slice(0, 200))))()', timeout=30)
print("STATE:", st)
print("SOURCES:", json.loads(srcs))
print("=== PLAYER TEXT ===")
print(full)
