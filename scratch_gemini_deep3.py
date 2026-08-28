"""Deep read-only probe of gemini after the NO_VIDEO failure (worklog #1123).

Video mode was enabled by operator, submit fired, but no video URL in 420s. Find out what
actually happened: did the prompt land? is there a video element? an error? a download link?
Also grab qwen's FULL video URL (poll output truncated it).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

GEMINI_JS = r"""
(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const out = {url: location.href};
  // videos
  out.videos = Array.from(document.querySelectorAll("video")).map(v => (v.currentSrc || v.src || "").slice(0, 100));
  // any mp4/video links or download buttons
  out.links = Array.from(document.querySelectorAll("a[href]")).map(a => a.href).filter(h => /mp4|video|download/i.test(h)).slice(0, 8);
  out.dlButtons = [];
  document.querySelectorAll("button,a,[role='button']").forEach(el => {
    if (!vis(el)) return;
    const lbl = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).replace(/\s+/g, " ").trim();
    if (/download|video|save|export/i.test(lbl)) out.dlButtons.push(lbl.slice(0, 50));
  });
  out.dlButtons = out.dlButtons.slice(0, 10);
  // composer state
  const input = Array.from(document.querySelectorAll("textarea,[contenteditable='true']")).find(vis);
  out.composer = input ? JSON.stringify((input.value || input.innerText || "").slice(0, 80)) : "NONE";
  // stop / generating indicators
  out.stopBtns = [];
  document.querySelectorAll("button,[role='button']").forEach(el => {
    if (!vis(el)) return;
    const lbl = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).replace(/\s+/g, " ").trim();
    if (/stop|cancel/i.test(lbl)) out.stopBtns.push(lbl.slice(0, 40));
  });
  // error text
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-400);
  // mode indicator
  const modeEl = Array.from(document.querySelectorAll("[aria-label*='mode' i],[aria-label*='video' i]")).filter(vis).slice(0,5).map(e => e.getAttribute("aria-label"));
  out.modeLabels = modeEl;
  return out;
})()
"""

QWEN_JS = r"""
(() => {
  const vids = Array.from(document.querySelectorAll("video")).map(v => (v.currentSrc || v.src || "")).filter(Boolean);
  const links = Array.from(document.querySelectorAll("a[href]")).map(a => a.href).filter(h => /mp4|video|cdn/i.test(h));
  return {videos: vids, links: links.slice(0, 5)};
})()
"""

lines = []

# gemini
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
if port:
    try:
        with Page(match="gemini.google.com", timeout=15, port=port) as pg:
            r = pg.evaluate(GEMINI_JS, timeout=30)
        lines.append("== GEMINI ==")
        for k in ("url", "videos", "links", "dlButtons", "composer", "stopBtns", "modeLabels"):
            lines.append(f"   {k}: {r.get(k)}")
        lines.append(f"   tail: {r.get('tail')!r}")
    except Exception as e:
        lines.append(f"gemini ERR {type(e).__name__}: {str(e)[:90]}")
else:
    lines.append("gemini: NO_TAB")

# qwen full url
port = None
for p in (9222, 9223, 9224, 9225):
    try:
        for t in list_targets(port=p):
            if t.get("type") == "page" and "chat.qwen.ai" in (t.get("url") or ""):
                port = p
                break
    except Exception:
        continue
    if port:
        break
if port:
    try:
        with Page(match="chat.qwen.ai", timeout=15, port=port) as pg:
            r = pg.evaluate(QWEN_JS, timeout=30)
        lines.append("== QWEN FULL URL ==")
        lines.append(f"   videos: {r.get('videos')}")
        lines.append(f"   links: {r.get('links')}")
    except Exception as e:
        lines.append(f"qwen ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_qwen_deep3.txt").write_text(report, encoding="utf-8")
