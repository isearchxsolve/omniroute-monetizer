"""Read-only check: did the sweep's earlier submits to gemini/grok/qwen produce a video?

The sweep submitted ~30 min ago. If a video finished rendering since, its URL is in the
DOM right now and we can recover it WITHOUT spending another credit. Never clicks,
never submits.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

PROBE = r"""
(() => {
  const out = {url: location.href, videos: [], links: [], busy: false, errText: ""};
  document.querySelectorAll("video").forEach(v => {
    const s = v.currentSrc || v.src || "";
    if (s) out.videos.push(s.slice(0, 120));
    v.querySelectorAll("source").forEach(so => {
      if (so.src) out.videos.push(so.src.slice(0, 120));
    });
  });
  document.querySelectorAll("a[href]").forEach(a => {
    if (/\.(mp4|webm|mov|m4v)(\?|$)/i.test(a.getAttribute("href") || ""))
      out.links.push(a.getAttribute("href").slice(0, 120));
  });
  out.busy = !!document.querySelector("[class*='spin' i],[class*='loading' i],[class*='progress' i],[aria-busy='true']");
  const txt = (document.body ? document.body.innerText : "").toLowerCase();
  ["failed", "error", "couldn't", "unable", "try again", "can't generate"].forEach(w => {
    if (txt.includes(w) && !out.errText) out.errText = w;
  });
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
        lines.append(f"{host:20s} NO_TAB")
        continue
    try:
        with Page(match=match, timeout=30, port=port) as pg:
            r = pg.evaluate(PROBE, timeout=60)
        if not isinstance(r, dict):
            lines.append(f"{host:20s} PROBE_NONE {r!r}")
            continue
        if r.get("videos") or r.get("links"):
            state = "VIDEO_FOUND"
        elif r.get("busy"):
            state = "STILL_BUSY"
        elif r.get("errText"):
            state = f"ERROR({r['errText']})"
        else:
            state = "NOTHING"
        lines.append(f"{host:20s} :{port} {state:14s} videos={r.get('videos')} "
                     f"links={r.get('links')} busy={r.get('busy')}")
    except Exception as e:
        lines.append(f"{host:20s} ERR {type(e).__name__}: {str(e)[:90]}")

report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_video_recover_probe.txt").write_text(
    report, encoding="utf-8")
