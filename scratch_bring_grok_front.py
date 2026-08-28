"""Bring the grok tab to the front so the operator can select the video option (worklog #1123)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

port = None
tid = None
for p in (9222, 9223, 9224, 9225):
    try:
        for t in list_targets(port=p):
            if t.get("type") == "page" and "grok.com" in (t.get("url") or ""):
                port = p
                tid = t.get("id")
                break
    except Exception:
        continue
    if port:
        break

if not port:
    print("grok tab NOT FOUND")
else:
    # Activate the target (brings its window + tab to front)
    try:
        with Page(match="grok.com", timeout=15, port=port) as pg:
            pg.send("Target.activateTarget", {"targetId": tid}, timeout=10)
            pg.evaluate("window.focus(); 1", timeout=10)
        print(f"grok tab brought to front on :{port} (target {tid})")
    except Exception as e:
        print(f"activate ERR {type(e).__name__}: {str(e)[:90]}")
