"""Read-only: full text of P2 tab, plus tiles count (lighthouse render watch)."""
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page
import flow_ui_client as f

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    full = pg.evaluate("(() => document.body.innerText)()", timeout=30)
    st = pg.evaluate(f.JS_RENDER_STATE, timeout=60)
print("LEN:", len(full), "| STATE:", st)
print("=== TEXT ===")
print(full)
