"""Read-only probe of the seat1 Flow tab (:9222) — follows the SPA redirect."""
import json
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

with Page(match="flow.google.com/", timeout=30, port=9222) as pg:
    url = pg.evaluate("(() => location.href)()", timeout=30)
    txt = pg.evaluate("(() => document.body.innerText.slice(0, 900))()", timeout=30)
print("current url:", url)
print("--- tab text ---")
print(txt)
