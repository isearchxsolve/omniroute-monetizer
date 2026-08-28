"""Dump gemini's currently-open '+' menu (operator opened it by hand, worklog #1123).

Read-only: just read the visible menu items so we can find the video option and build
the click gesture.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

DUMP_JS = r"""
(() => {
  const out = {items: [], overlays: []};
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  document.querySelectorAll("[role='menuitem'],[role='option'],[role='menuitemradio'],mat-menu-item,.mat-mdc-menu-item,[class*='menu-item' i],[class*='menu_item' i]").forEach(el => {
    if (!vis(el)) return;
    const txt = (el.innerText || "").replace(/\s+/g, " ").trim();
    if (txt) out.items.push({txt: txt.slice(0, 80), role: el.getAttribute("role") || "", cls: String(el.className).slice(0, 60)});
  });
  // Any visible overlay/popover text (the menu container)
  document.querySelectorAll("[class*='overlay' i],[class*='menu' i],[class*='picker' i],[class*='popover' i],[class*='panel' i],[class*='dropdown' i]").forEach(el => {
    if (!vis(el)) return;
    const t = (el.innerText || "").replace(/\s+/g, " ").trim();
    if (t && t.length < 300) out.overlays.push(t.slice(0, 200));
  });
  out.overlays = out.overlays.slice(0, 6);
  return out;
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
        r = pg.evaluate(DUMP_JS, timeout=30)
    lines.append(f"menu items ({len(r.get('items', []))}):")
    for it in r.get("items", []):
        lines.append(f"   [{it['role']}] {it['txt']!r}  cls={it['cls']}")
    lines.append(f"overlays: {r.get('overlays')}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_plus_menu.txt").write_text(report, encoding="utf-8")
