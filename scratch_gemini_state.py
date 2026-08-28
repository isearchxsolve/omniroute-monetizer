"""Check gemini composer visibility + stop button (worklog #1123).

The '+' tool button only appears when the composer is visible. While a response is
generating, the composer is hidden and a stop button shows instead. Determine state.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

STATE_JS = r"""
(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const out = {};
  const ta = Array.from(document.querySelectorAll("textarea")).find(vis);
  const ce = Array.from(document.querySelectorAll("[contenteditable='true'],[contenteditable='plaintext-only']")).find(vis);
  out.composerVisible = !!(ta || ce);
  out.composerKind = ta ? "textarea" : (ce ? "contenteditable" : "none");
  if (ce) out.composerText = (ce.innerText || "").slice(0, 120);
  // Stop / cancel button?
  out.stopBtns = Array.from(document.querySelectorAll("button,[role='button']"))
    .filter(el => vis(el) && /stop|cancel|halt/i.test((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")))
    .map(el => ((el.getAttribute("aria-label") || "") + " / " + (el.innerText || "")).replace(/\s+/g, " ").trim().slice(0, 60));
  // Spinner still there?
  out.spinner = !!document.querySelector("mat-progress-spinner,.loading-content-spinner-container");
  // Last response area text
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-250);
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
        r = pg.evaluate(STATE_JS, timeout=30)
    for k, v in r.items():
        lines.append(f"{k}: {v!r}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_state.txt").write_text(report, encoding="utf-8")
