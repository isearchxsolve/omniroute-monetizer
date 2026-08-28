"""Deep read-only look at gemini's actual state after 420s of 'BUSY' (worklog #1123).

The busy detector matched BODY.enable-lm-loading-animation — a body class that may be
permanent, not a real render signal. Check: video elements (incl blob:), download
buttons, the conversation tail, and any error text.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

DEEP_JS = r"""
(() => {
  const out = {url: location.href};
  // ALL video elements, including blob:
  out.videos = Array.from(document.querySelectorAll("video")).map(v => ({
    src: (v.currentSrc || v.src || "").slice(0, 100),
    ready: v.readyState, paused: v.paused
  }));
  // Download / open buttons
  out.dlButtons = Array.from(document.querySelectorAll("button,a,[role='button']"))
    .filter(el => /download|save|open|export/i.test((el.getAttribute("aria-label")||"") + " " + (el.innerText||"")))
    .map(el => ((el.getAttribute("aria-label")||"") + " / " + (el.innerText||"")).replace(/\s+/g," ").trim().slice(0,60))
    .slice(0, 8);
  // Which elements actually match the busy selector?
  out.busyMatches = Array.from(document.querySelectorAll("[class*='spin' i],[class*='loading' i],[class*='progress' i],[aria-busy='true']"))
    .slice(0, 6).map(el => el.tagName + "." + String(el.className).slice(0, 70));
  // Conversation tail
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-500);
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
        r = pg.evaluate(DEEP_JS, timeout=30)
    lines.append(f"url: {r.get('url')}")
    lines.append(f"videos: {r.get('videos')}")
    lines.append(f"dlButtons: {r.get('dlButtons')}")
    lines.append(f"busyMatches: {r.get('busyMatches')}")
    lines.append(f"tail: {r.get('tail')!r}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_deep2.txt").write_text(report, encoding="utf-8")
