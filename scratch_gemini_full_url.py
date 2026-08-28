"""Grab the FULL gemini video URL + verify it's a real video (worklog #1123)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

JS = r"""
(() => {
  const out = {url: location.href};
  out.videos = Array.from(document.querySelectorAll("video")).map(v => (v.currentSrc || v.src || "")).filter(Boolean);
  out.links = Array.from(document.querySelectorAll("a[href]")).map(a => a.href)
    .filter(h => /usercontent\.google|\.mp4(\?|$)|googlevideo\.com|storage\/googleapis|contribution/i.test(h));
  // any download button href
  out.dl = [];
  document.querySelectorAll("a[href]").forEach(a => {
    const lbl = ((a.getAttribute("aria-label") || "") + " " + (a.innerText || "")).replace(/\s+/g," ").trim();
    if (/download|save/i.test(lbl)) out.dl.push({lbl: lbl.slice(0,40), href: a.href});
  });
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
    lines.append("gemini: NO_TAB")
else:
    try:
        with Page(match="gemini.google.com", timeout=15, port=port) as pg:
            r = pg.evaluate(JS, timeout=30)
        lines.append(f"url: {r.get('url')}")
        lines.append(f"videos: {r.get('videos')}")
        lines.append(f"links: {r.get('links')}")
        lines.append(f"dl: {r.get('dl')}")
    except Exception as e:
        lines.append(f"ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_full_url.txt").write_text(report, encoding="utf-8")
