"""Real coordinate click on gemini 'Create video' via CDP Input.dispatchMouseEvent.

Synthetic el.click() did not toggle the Angular Material menuitemcheckbox (aria-checked
stayed false). A real mouse press+release at the element's center is what Chrome's user
produces. Menu is still open (operator opened it). Spend nothing — only toggles mode.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

RECT_JS = r"""
(() => {
  const items = Array.from(document.querySelectorAll("[role='menuitemcheckbox'],[class*='toolbox-drawer-menu-item' i],[class*='menu-item' i]"));
  const pick = items.find(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && /create video/i.test((el.innerText || "").trim());
  });
  if (!pick) return null;
  const r = pick.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height,
          txt: (pick.innerText || "").trim(), checked: pick.getAttribute("aria-checked")};
})()
"""

VERIFY_JS = r"""
(() => {
  const items = Array.from(document.querySelectorAll("[role='menuitemcheckbox']"));
  const vid = items.find(el => /create video/i.test((el.innerText || "").trim()));
  const txt = (document.body ? document.body.innerText : "");
  return {
    videoChecked: vid ? vid.getAttribute("aria-checked") : "item-gone",
    menuStillOpen: /Create music/.test(txt),
    tail: txt.replace(/\n+/g, " | ").slice(-200)
  };
})()
"""

port = None
for p in (9222, 9223, 9224, 9225):
    try:
        for t in list_targets(port=p):
            if t.get("type") == "page" and "gemini.google.com" in (t.get("url") or ""):
                port = p
                break
    except Exception:
        continue
    if port:
        break

lines = []
if not port:
    lines.append("NO_TAB")
else:
    with Page(match="gemini.google.com", timeout=15, port=port) as pg:
        rect = pg.evaluate(RECT_JS, timeout=30)
        lines.append(f"target rect: {rect}")
        if not rect:
            lines.append("no visible 'Create video' — menu may have closed")
        else:
            x, y = rect["x"], rect["y"]
            pg.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, timeout=15)
            pg.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                                 "button": "left", "clickCount": 1}, timeout=15)
            pg.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                                 "button": "left", "clickCount": 1}, timeout=15)
            lines.append(f"dispatched real click at ({x:.0f},{y:.0f})")
            time.sleep(1.5)
            v = pg.evaluate(VERIFY_JS, timeout=30)
            lines.append(f"videoChecked: {v.get('videoChecked')}")
            lines.append(f"menuStillOpen: {v.get('menuStillOpen')}")
            lines.append(f"tail: {v.get('tail')!r}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_realclick.txt").write_text(report, encoding="utf-8")
