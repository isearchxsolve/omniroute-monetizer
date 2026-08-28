"""Deep read-only probe of grok after the video-explicit NO_VIDEO failure (worklog #1123).

Prompt was 'Generate a video: a red ball...'. Did it land? Did grok generate an IMAGE instead
of a video (Imagine defaults to image)? Is there an error? a video element? a 'make it a video'
option? Dump composer, last assistant turn, any media, and video-ish buttons.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

GROK_JS = r"""
(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const out = {url: location.href};
  // composer
  const input = Array.from(document.querySelectorAll("textarea,[contenteditable='true'],[contenteditable='plaintext-only']")).find(vis);
  out.composer = input ? (input.tagName + " val=" + JSON.stringify((input.value || input.innerText || "").slice(0, 80))) : "NONE";
  // media elements
  out.videos = Array.from(document.querySelectorAll("video")).map(v => (v.currentSrc || v.src || "").slice(0, 100));
  out.imgs = Array.from(document.querySelectorAll("img")).map(i => i.src).filter(s => /grok|imag|x\.ai|cdn/i.test(s)).slice(-6);
  // video-ish / imagine-ish buttons
  out.mediaButtons = [];
  document.querySelectorAll("button,a,[role='button'],[role='tab'],[role='menuitem']").forEach(el => {
    if (!vis(el)) return;
    const lbl = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).replace(/\s+/g, " ").trim();
    if (/video|imagine|image|animat|motion|generat|create|media/i.test(lbl)) out.mediaButtons.push({tag: el.tagName, lbl: lbl.slice(0, 50)});
  });
  out.mediaButtons = out.mediaButtons.slice(0, 15);
  // stop / error
  out.stopBtns = [];
  document.querySelectorAll("button,[role='button']").forEach(el => {
    if (!vis(el)) return;
    const lbl = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).replace(/\s+/g, " ").trim();
    if (/stop|cancel/i.test(lbl)) out.stopBtns.push(lbl.slice(0, 40));
  });
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-400);
  return out;
})()
"""

port = None
for p in (9222, 9223, 9224, 9225):
    try:
        for t in list_targets(port=p):
            if t.get("type") == "page" and "grok.com" in (t.get("url") or ""):
                port = p
                break
    except Exception:
        continue
    if port:
        break

lines = []
if not port:
    lines.append("grok: NO_TAB")
else:
    try:
        with Page(match="grok.com", timeout=15, port=port) as pg:
            r = pg.evaluate(GROK_JS, timeout=30)
        for k in ("url", "composer", "videos", "imgs", "mediaButtons", "stopBtns"):
            lines.append(f"   {k}: {r.get(k)}")
        lines.append(f"   tail: {r.get('tail')!r}")
    except Exception as e:
        lines.append(f"grok ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_grok_deep.txt").write_text(report, encoding="utf-8")
