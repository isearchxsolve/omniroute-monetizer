"""Re-probe gemini + grok video tabs (read-only) to finalize classification."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

PROBE = r"""
(() => {
  const txt = (document.body ? document.body.innerText : '').toLowerCase();
  const has = (arr) => arr.filter(w => txt.includes(w));
  const paywall = has(['upgrade','out of credits','no credits','insufficient','buy credits','0 credits','subscribe','quota','limit reached','exceeded']);
  const videoEl = document.querySelectorAll('video').length;
  const spinner = !!document.querySelector("[class*='spin' i],[class*='loading' i],[class*='progress' i],[aria-busy='true']");
  let mediaUrl=''; const v=document.querySelector('video'); if(v){mediaUrl=v.currentSrc||v.src||'';}
  return {url:location.href, pw:paywall.slice(0,3), vid:videoEl, media:(mediaUrl||'').slice(0,70), spin:spinner};
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
for host, match in [("gemini.google.com", "gemini.google.com"), ("grok.com", "grok.com")]:
    port = find(match)
    if not port:
        lines.append(host + " NO_TAB")
        continue
    try:
        with Page(match=match, timeout=30, port=port) as pg:
            r = pg.evaluate(PROBE, timeout=40)
        lines.append(host + " :" + str(port) + " " + repr(r))
    except Exception as e:
        lines.append(host + " ERR " + type(e).__name__ + " " + str(e)[:80])

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_video_reprobe.txt").write_text(
    report, encoding="utf-8")
