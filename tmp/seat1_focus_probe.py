"""Read-only focus/visibility diagnostics for the seat1 Flow tab (:9222)."""
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

FOCUS_JS = (
    "(() => { const v = el => { const r = el.getBoundingClientRect();"
    " return r.width > 0 && r.height > 0; };"
    " const ce = Array.from(document.querySelectorAll('[contenteditable=\"true\"]'))"
    "   .find(v); if (!ce) return 'NO_CE'; ce.focus(); return 'FOCUSED'; })()"
)

with Page(match="flow.google.com/project/", timeout=30, port=9222) as pg:
    print("focus:", pg.evaluate(FOCUS_JS, timeout=30))
    print("document.hasFocus:", pg.evaluate("(() => document.hasFocus())()", timeout=30))
    print("visibility:", pg.evaluate("(() => document.visibilityState)()", timeout=30))
