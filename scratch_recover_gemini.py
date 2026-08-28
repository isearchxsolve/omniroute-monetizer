"""Recover gemini's in-flight video render (worklog #1123).

The killed re-run had already injected (duplicated prompt — the bug the operator spotted,
now fixed with select-all-replace) and clicked generate before being stopped. Gemini is
rendering. Both prompt halves describe the same red-ball scene, so the output is valid.
This script only POLLS the DOM read-only — never clicks, never submits, never spends.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

from cdp import Page, list_targets  # noqa: E402

POLL_JS = r"""
(() => {
  const out = {videos: [], links: [], busy: false, errText: ""};
  document.querySelectorAll("video").forEach(v => {
    const s = v.currentSrc || v.src || "";
    if (s && !s.startsWith("blob:")) out.videos.push(s.slice(0, 160));
    v.querySelectorAll("source").forEach(so => {
      if (so.src && !so.src.startsWith("blob:")) out.videos.push(so.src.slice(0, 160));
    });
  });
  document.querySelectorAll("a[href]").forEach(a => {
    const h = a.getAttribute("href") || "";
    if (/\.(mp4|webm|mov|m4v)(\?|$)/i.test(h)) out.links.push(h.slice(0, 160));
  });
  out.busy = !!document.querySelector("[class*='spin' i],[class*='loading' i],[class*='progress' i],[aria-busy='true']");
  const txt = (document.body ? document.body.innerText : "").toLowerCase();
  ["couldn't generate", "unable to", "try again later", "can't generate", "something went wrong"].forEach(w => {
    if (txt.includes(w) && !out.errText) out.errText = w;
  });
  return out;
})()
"""

BUDGET_S = 420
START = time.time()
lines = []
found = None
while time.time() - START < BUDGET_S:
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
    if not port:
        lines.append(f"t={int(time.time()-START):4d}s NO_TAB")
        time.sleep(5)
        continue
    try:
        with Page(match="gemini.google.com", timeout=15, port=port) as pg:
            r = pg.evaluate(POLL_JS, timeout=30)
        if isinstance(r, dict) and (r.get("videos") or r.get("links")):
            found = (r.get("videos") or r.get("links"))[0]
            lines.append(f"t={int(time.time()-START):4d}s VIDEO_FOUND {found}")
            break
        state = "BUSY" if (r or {}).get("busy") else ("ERR:" + (r or {}).get("errText", "?") if (r or {}).get("errText") else "IDLE")
        lines.append(f"t={int(time.time()-START):4d}s {state}")
    except Exception as e:
        lines.append(f"t={int(time.time()-START):4d}s ERR {type(e).__name__}: {str(e)[:70]}")
    time.sleep(10)

if not found:
    lines.append(f"TIMEOUT after {BUDGET_S}s — no video URL surfaced")
report = "\n".join(lines)
print(report)
pathlib.Path(__file__).resolve().parent.joinpath("_gemini_recover.txt").write_text(report, encoding="utf-8")
