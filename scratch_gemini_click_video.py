"""Click gemini's 'Create video' menu item (menu already open, worklog #1123).

The '+' toolbox drawer exposes a 'Create video' menuitemcheckbox — the video-mode toggle
the operator pointed to. Click it, then verify the composer switched into video mode.
Toggling the mode spends nothing; only the eventual send burns a Veo credit.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

CLICK_VIDEO_JS = r"""
(() => {
  const items = Array.from(document.querySelectorAll("[role='menuitemcheckbox'],[role='menuitem'],[class*='toolbox-drawer-menu-item' i]"));
  const pick = items.find(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && /^create video$/i.test((el.innerText || "").trim());
  });
  if (!pick) return {ok: false, why: "no visible 'Create video' item"};
  const before = pick.getAttribute("aria-checked");
  pick.click();
  return {ok: true, before, label: (pick.innerText || "").trim()};
})()
"""

VERIFY_JS = r"""
(() => {
  const out = {};
  // Is the Create video item now checked?
  const items = Array.from(document.querySelectorAll("[role='menuitemcheckbox']"));
  const vid = items.find(el => /^create video$/i.test((el.innerText || "").trim()));
  out.videoChecked = vid ? vid.getAttribute("aria-checked") : "item-gone";
  // Composer state: any video-mode chip / hint near the input?
  const txt = (document.body ? document.body.innerText : "");
  out.mentionsVideo = /video/i.test(txt.slice(-800));
  const tail = txt.replace(/\n+/g, " | ");
  out.tail = tail.slice(-250);
  // Is a generation still running (stop button present)?
  out.stopPresent = !!Array.from(document.querySelectorAll("button,[role='button'],[aria-label]"))
    .find(el => /stop/i.test(el.getAttribute("aria-label") || ""));
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
        r1 = pg.evaluate(CLICK_VIDEO_JS, timeout=30)
        lines.append(f"click Create video: {r1}")
        time.sleep(1.5)
        r2 = pg.evaluate(VERIFY_JS, timeout=30)
        lines.append(f"videoChecked: {r2.get('videoChecked')}")
        lines.append(f"stopPresent: {r2.get('stopPresent')}")
        lines.append(f"tail: {r2.get('tail')!r}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_click_video.txt").write_text(report, encoding="utf-8")
