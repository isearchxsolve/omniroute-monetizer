"""Probe gemini's mode picker menu (worklog #1123).

Operator: "you have to select video option for generating video". The tab is in text
mode (Pro Extended). Click the mode picker to open it and dump the menu options so we
can find the video/Veo entry. Opening the menu spends nothing.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

OPEN_PICKER_JS = r"""
(() => {
  const btns = Array.from(document.querySelectorAll("button,[role='button']"));
  const pick = btns.find(b => /mode picker/i.test(b.getAttribute("aria-label") || ""));
  if (!pick) return {ok: false, why: "no mode picker button"};
  pick.click();
  return {ok: true, label: (pick.getAttribute("aria-label") || "").slice(0, 80)};
})()
"""

DUMP_MENU_JS = r"""
(() => {
  const out = {items: []};
  // Menu items are usually mat-menu-item / role=menuitem / role=option
  document.querySelectorAll("[role='menuitem'],[role='option'],mat-menu-item,.mat-mdc-menu-item,[class*='menu-item' i]").forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    const txt = (el.innerText || "").replace(/\s+/g, " ").trim();
    if (txt) out.items.push({txt: txt.slice(0, 80), role: el.getAttribute("role") || "", cls: String(el.className).slice(0, 50)});
  });
  // Also grab any visible overlay text mentioning video/veo
  const overlays = Array.from(document.querySelectorAll("[class*='overlay' i],[class*='menu' i],[class*='picker' i],[class*='popover' i]"))
    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  out.overlayText = overlays.map(el => (el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 200)).slice(0, 4);
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
        r1 = pg.evaluate(OPEN_PICKER_JS, timeout=30)
        lines.append(f"open picker: {r1}")
        time.sleep(1.5)
        r2 = pg.evaluate(DUMP_MENU_JS, timeout=30)
        lines.append(f"menu items ({len(r2.get('items', []))}):")
        for it in r2.get("items", []):
            lines.append(f"   [{it['role']}] {it['txt']!r}  cls={it['cls']}")
        lines.append(f"overlayText: {r2.get('overlayText')}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_picker.txt").write_text(report, encoding="utf-8")
