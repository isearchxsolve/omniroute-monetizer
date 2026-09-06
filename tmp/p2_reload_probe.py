"""Reload the P2 project tab (safe now - renders terminal) and re-check tiles."""
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    pg.send("Page.navigate",
            {"url": "https://flow.google.com/project/1d8d0d9f-ba25-450d-ad0b-27ef39c619e9"},
            timeout=60)
    time.sleep(18)
    st = pg.evaluate(
        '(() => JSON.stringify({tiles: document.querySelectorAll("video").length,'
        ' len: document.body.innerText.length}))()', timeout=30)
print("after reload:", st)
