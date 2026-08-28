"""Deeper read-only diagnosis of gemini/grok/qwen video tabs (worklog #1123)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

DEEP_JS = r"""
(() => {
  const out = {url: location.href};
  // What is the busy element, actually?
  const busy = document.querySelector("[class*='spin' i],[class*='loading' i],[class*='progress' i],[aria-busy='true']");
  if (busy) {
    out.busyTag = busy.tagName + "." + String(busy.className).slice(0, 80);
    out.busyText = (busy.innerText || "").trim().slice(0, 100);
  }
  // Last ~400 chars of visible text (where errors/status usually sit).
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-400);
  // Did our prompt land anywhere visible?
  out.promptSeen = txt.toLowerCase().includes("red ball");
  // Any generate-ish buttons currently enabled?
  const btns = Array.from(document.querySelectorAll("button,[role='button']"))
    .filter(b => { const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !b.disabled; })
    .map(b => ((b.getAttribute("aria-label") || "") + " / " + (b.innerText || "")).replace(/\s+/g, " ").trim().slice(0, 50))
    .filter(Boolean);
  out.buttons = btns.slice(0, 12);
  return out;
})()
"""


def find(match):
    for port in (9222, 9223, 9224, 9225):
        try:
            for t in list_targets(port=port):
                if t.get("type") == "page" and match in (t.get("url") or ""):
                    return port
        except Exception:
            continue
    return None


lines = []
for host, match in [("gemini.google.com", "gemini.google.com"),
                    ("grok.com", "grok.com"),
                    ("chat.qwen.ai", "chat.qwen.ai")]:
    port = find(match)
    if not port:
        lines.append(f"== {host}: NO_TAB")
        continue
    try:
        with Page(match=match, timeout=30, port=port) as pg:
            r = pg.evaluate(DEEP_JS, timeout=60)
        lines.append(f"== {host} :{port}")
        lines.append(f"   url: {r.get('url')}")
        lines.append(f"   busy: {r.get('busyTag')} | {r.get('busyText')!r}")
        lines.append(f"   promptSeen: {r.get('promptSeen')}")
        lines.append(f"   buttons: {r.get('buttons')}")
        lines.append(f"   tail: {r.get('tail')!r}")
    except Exception as e:
        lines.append(f"== {host}: ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_video_deep_probe.txt").write_text(
    report, encoding="utf-8")
