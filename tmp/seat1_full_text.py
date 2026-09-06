"""Read-only: dump the seat1 Flow tab's full innerText + composer state."""
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page
import flow_ui_client as f

with Page(match="flow.google.com/project/", timeout=30, port=9222) as pg:
    full = pg.evaluate("(() => document.body.innerText)()", timeout=30)
    ready = pg.evaluate(f.JS_COMPOSER_READY, timeout=30)
    st = pg.evaluate(f.JS_RENDER_STATE, timeout=60)
print("LEN:", len(full))
print("COMPOSER:", ready)
print("RENDER_STATE:", st)
print("=== TEXT ===")
print(full)
