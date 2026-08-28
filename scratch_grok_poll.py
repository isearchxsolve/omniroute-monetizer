"""Read-only poller: watch the grok tab for the video URL from the operator's generation.

Operator confirmed the prompt was injected but NEVER submitted (send click didn't fire) —
same class-a send-button gap as gemini. Operator is submitting manually. Do NOT inject or
click anything — just poll for a <video> element / mp4 URL until it appears or budget ends.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

BUDGET_S = 420

POLL_JS = r"""
(() => {
  const out = {url: location.href};
  const vids = Array.from(document.querySelectorAll("video"));
  out.videos = vids.map(v => (v.currentSrc || v.src || "")).filter(Boolean);
  // only real media URLs — exclude analytics/nav links
  const links = Array.from(document.querySelectorAll("a[href]")).map(a => a.href)
    .filter(h => /\.mp4(\?|$)|\.webm(\?|$)|video|cdn/i.test(h) && !/adsct|analytics|t\.co/i.test(h));
  out.links = links.slice(0, 5);
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-200);
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
    t0 = time.time()
    found = None
    while time.time() - t0 < BUDGET_S:
        try:
            with Page(match="grok.com", timeout=15, port=port) as pg:
                r = pg.evaluate(POLL_JS, timeout=30)
            vids = r.get("videos") or []
            links = r.get("links") or []
            urls = [u for u in vids + links if u and not u.startswith("blob:")]
            blob = [u for u in vids if u.startswith("blob:")]
            if urls:
                found = urls[0]
                lines.append(f"grok LIVE  {time.time()-t0:6.1f}s  url={found[:140]}")
                break
            if blob:
                lines.append(f"grok BLOB  {time.time()-t0:6.1f}s  (video element present, blob src — rendering)")
            else:
                lines.append(f"grok BUSY  {time.time()-t0:6.1f}s  tail={r.get('tail','')[-120:]!r}")
        except Exception as e:
            lines.append(f"grok ERR   {time.time()-t0:6.1f}s  {type(e).__name__}: {str(e)[:80]}")
        time.sleep(15)
    if not found:
        lines.append(f"grok TIMEOUT after {BUDGET_S}s — no non-blob video URL surfaced")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_grok_poll.txt").write_text(report, encoding="utf-8")
