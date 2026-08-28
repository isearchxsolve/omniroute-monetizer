"""Probe grok + qwen video-mode entry points (worklog #1123).

Both returned NO_VIDEO after inject+generate fired. Operator's gemini insight: video needs
an explicit mode selection. Check whether grok/qwen have a video/imagine mode toggle that
the generic generate-click missed. Read-only: dump composer toolbar + any video-ish toggles.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

PROBE_JS = r"""
(() => {
  const out = {url: location.href};
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  // Composer input
  const input = Array.from(document.querySelectorAll("textarea,[contenteditable='true'],[contenteditable='plaintext-only']")).find(vis);
  out.composer = input ? (input.tagName + " val=" + JSON.stringify((input.value || input.innerText || "").slice(0, 60))) : "NONE";
  // Buttons/toggles near composer or mentioning video/imagine/wan
  out.videoish = [];
  document.querySelectorAll("button,[role='button'],[role='tab'],[role='menuitem'],[role='menuitemcheckbox'],a").forEach(el => {
    if (!vis(el)) return;
    const lbl = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).replace(/\s+/g, " ").trim();
    if (/video|imagine|veo|wan|create|generat|media|image/i.test(lbl)) out.videoish.push({tag: el.tagName, role: el.getAttribute("role") || "", lbl: lbl.slice(0, 60), checked: el.getAttribute("aria-checked")});
  });
  out.videoish = out.videoish.slice(0, 15);
  // Any video element or error text
  out.videos = Array.from(document.querySelectorAll("video")).map(v => (v.currentSrc || v.src || "").slice(0, 80));
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-300);
  return out;
})()
"""

lines = []
for match in ("grok.com", "chat.qwen.ai"):
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
            r = pg.evaluate(PROBE_JS, timeout=30)
        lines.append(f"== {match} :{port}")
        lines.append(f"   url: {r.get('url')}")
        lines.append(f"   composer: {r.get('composer')}")
        lines.append(f"   videoish: {r.get('videoish')}")
        lines.append(f"   videos: {r.get('videos')}")
        lines.append(f"   tail: {r.get('tail')!r}")
    except Exception as e:
        lines.append(f"== {match}: ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_grok_qwen_video_entry.txt").write_text(report, encoding="utf-8")
