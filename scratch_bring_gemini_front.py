"""Bring the gemini tab to the front so the operator can inspect it (worklog #1123)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

port = None
tid = None
for p in (9222, 9223, 9224, 9225):
    try:
        for t in list_targets(port=p):
            if t.get("type") == "page" and "gemini.google.com" in (t.get("url") or ""):
                port = p
                tid = t.get("id")
                break
    except Exception:
        continue
    if port:
        break

if not port:
    print("gemini tab NOT FOUND")
else:
    try:
        with Page(match="gemini.google.com", timeout=15, port=port) as pg:
            pg.send("Target.activateTarget", {"targetId": tid}, timeout=10)
            pg.evaluate("window.focus(); 1", timeout=10)
        print(f"gemini tab brought to front on :{port} (target {tid})")
    except Exception as e:
        print(f"activate ERR {type(e).__name__}: {str(e)[:90]}")
