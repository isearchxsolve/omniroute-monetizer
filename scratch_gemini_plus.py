"""Click gemini's '+' button (left of composer) and dump the menu (worklog #1123).

Operator: "the plus sign on left has it click on it". The video option lives in that
menu. Opening it spends nothing.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

CLICK_PLUS_JS = r"""
(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const btns = Array.from(document.querySelectorAll("button,[role='button']")).filter(el => vis(el) && !el.disabled);
  // Candidates: aria-label or text containing 'add' / '+' / 'plus', or literally '+'
  const cands = btns.filter(b => {
    const lbl = (b.getAttribute("aria-label") || "").toLowerCase();
    const txt = (b.innerText || "").trim();
    return /add|plus/.test(lbl) || txt === "+" || txt === "＋";
  });
  if (!cands.length) return {ok: false, why: "no + button found",
    all: btns.map(b => ((b.getAttribute("aria-label")||"") + " / " + (b.innerText||"")).replace(/\s+/g," ").trim()).filter(Boolean).slice(0, 25)};
  // Prefer the one nearest the composer (left of input)
  const input = Array.from(document.querySelectorAll("textarea,[contenteditable='true'],[contenteditable='plaintext-only']")).find(vis);
  let pick = cands[0];
  if (input) {
    const ir = input.getBoundingClientRect();
    pick = cands.map(b => { const r = b.getBoundingClientRect(); return {b, d: Math.hypot(r.x - ir.x, r.y - ir.y)}; })
                .sort((a, z) => a.d - z.d)[0].b;
  }
  const label = ((pick.getAttribute("aria-label") || "") + " / " + (pick.innerText || "")).replace(/\s+/g, " ").trim();
  pick.click();
  return {ok: true, picked: label.slice(0, 70), candidates: cands.length};
})()
"""

DUMP_MENU_JS = r"""
(() => {
  const out = {items: [], overlays: []};
  document.querySelectorAll("[role='menuitem'],[role='option'],[role='menu'] *,.mat-mdc-menu-item,mat-menu-item").forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    const txt = (el.innerText || "").replace(/\s+/g, " ").trim();
    if (txt && txt.length < 80) out.items.push(txt);
  });
  out.items = [...new Set(out.items)].slice(0, 20);
  Array.from(document.querySelectorAll("[class*='overlay' i],[class*='menu-panel' i],[class*='popover' i],[role='menu']"))
    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .forEach(el => out.overlays.push((el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 250)));
  out.overlays = out.overlays.slice(0, 4);
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
        r1 = pg.evaluate(CLICK_PLUS_JS, timeout=30)
        lines.append(f"click +: {r1}")
        time.sleep(1.5)
        r2 = pg.evaluate(DUMP_MENU_JS, timeout=30)
        lines.append(f"menu items: {r2.get('items')}")
        lines.append(f"overlays: {r2.get('overlays')}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_plus_menu.txt").write_text(report, encoding="utf-8")
