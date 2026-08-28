"""Read-only: what input surfaces do heygen/magichour actually have? (worklog #1123)"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

SURFACE_JS = r"""
(() => {
  const out = {url: location.href, inputs: [], editables: [], buttons: []};
  const vis = el => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const st = window.getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden';
  };
  document.querySelectorAll('textarea,input[type="text"],input:not([type]),input[type="search"]').forEach(el => {
    if (vis(el)) out.inputs.push({tag: el.tagName, type: el.type || '', ph: (el.placeholder || '').slice(0, 50),
      cls: String(el.className).slice(0, 60), id: el.id || ''});
  });
  document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"],[role="textbox"]').forEach(el => {
    if (vis(el)) out.editables.push({tag: el.tagName, role: el.getAttribute('role') || '',
      cls: String(el.className).slice(0, 60), txt: (el.innerText || '').slice(0, 40)});
  });
  document.querySelectorAll('button,[role="button"]').forEach(el => {
    if (vis(el) && !el.disabled) {
      const lbl = ((el.getAttribute('aria-label') || '') + ' / ' + (el.innerText || '')).replace(/\s+/g, ' ').trim();
      if (lbl) out.buttons.push(lbl.slice(0, 60));
    }
  });
  out.buttons = out.buttons.slice(0, 15);
  return out;
})()
"""

lines = []
for match in ("heygen.com", "magichour.ai"):
    port = None
    for p in (9222, 9223, 9224, 9225):
        try:
            for t in list_targets(port=p):
                if t.get("type") == "page" and match in (t.get("url") or ""):
                    port = p
                    break
        except Exception:
            continue
        if port:
            break
    if not port:
        lines.append(f"== {match}: NO_TAB")
        continue
    try:
        with Page(match=match, timeout=15, port=port) as pg:
            r = pg.evaluate(SURFACE_JS, timeout=30)
        lines.append(f"== {match} :{port}")
        lines.append(f"   url: {r.get('url')}")
        lines.append(f"   inputs: {r.get('inputs')}")
        lines.append(f"   editables: {r.get('editables')}")
        lines.append(f"   buttons: {r.get('buttons')}")
    except Exception as e:
        lines.append(f"== {match}: ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_heygen_magichour_surface.txt").write_text(
    report, encoding="utf-8")
