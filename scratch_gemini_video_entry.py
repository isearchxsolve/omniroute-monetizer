"""Probe gemini's video entry point (worklog #1123).

The mode picker only lists text models. Video (Veo) is reached via the sidebar "Videos"
nav or a composer tool button. Dump both surfaces to find the exact click target.
Opening menus / reading the DOM spends nothing.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

PROBE_JS = r"""
(() => {
  const out = {nav: [], composerTools: [], allVideoish: []};
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  // Sidebar nav links (a, button) mentioning Videos/Images
  document.querySelectorAll("a,button,[role='link'],[role='menuitem']").forEach(el => {
    if (!vis(el)) return;
    const txt = ((el.innerText || "") + " " + (el.getAttribute("aria-label") || "")).replace(/\s+/g, " ").trim();
    if (/^(videos?|images?|canvas|veo)/i.test(txt)) out.nav.push({tag: el.tagName, txt: txt.slice(0, 60), href: (el.getAttribute("href") || "").slice(0, 60)});
  });
  // Composer toolbar buttons (icons near the input)
  const input = Array.from(document.querySelectorAll("textarea,[contenteditable='true'],[contenteditable='plaintext-only']")).find(vis);
  if (input) {
    const ir = input.getBoundingClientRect();
    document.querySelectorAll("button,[role='button']").forEach(el => {
      if (!vis(el) || el.disabled) return;
      const r = el.getBoundingClientRect();
      // within ~120px of the composer
      if (Math.abs(r.y - ir.y) < 120 && Math.abs(r.x - ir.x) < 900) {
        const lbl = ((el.getAttribute("aria-label") || "") + " / " + (el.innerText || "")).replace(/\s+/g, " ").trim();
        if (lbl && lbl !== "/") out.composerTools.push(lbl.slice(0, 60));
      }
    });
  }
  // Anything anywhere mentioning video/veo
  document.querySelectorAll("*").forEach(el => {
    if (el.children.length > 0) return;
    if (!vis(el)) return;
    const t = (el.innerText || "").trim();
    if (/^(video|veo|generate video|create video)/i.test(t)) out.allVideoish.push({tag: el.tagName, txt: t.slice(0, 50), cls: String(el.className).slice(0, 40)});
  });
  out.allVideoish = out.allVideoish.slice(0, 10);
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
        r = pg.evaluate(PROBE_JS, timeout=30)
    lines.append(f"nav: {r.get('nav')}")
    lines.append(f"composerTools: {r.get('composerTools')}")
    lines.append(f"allVideoish: {r.get('allVideoish')}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_video_entry.txt").write_text(report, encoding="utf-8")
