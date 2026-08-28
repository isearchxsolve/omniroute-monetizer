"""Read-only diagnosis of the NO_VIDEO video seats (worklog #1122).

NO_VIDEO means the UI driver injected the prompt AND clicked a generate button,
but no video URL surfaced within 420s. That is ambiguous between:
  (b) zero credits  -> the site shows a paywall / upgrade / "out of credits" modal
  (a) slow render   -> a spinner/progress is still on screen
  (c) wrong surface -> the click hit a button that does not generate

This probe attaches to each host's live tab via raw CDP and READS the DOM only.
It never clicks, never submits, never spends a credit. It reports which of the
three states the page is in so we can classify honestly instead of declaring dead.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from cdp import Page, list_targets  # noqa: E402

# The NO_VIDEO hosts from the sweep, with the tab-match substring the video client uses.
HOSTS = {
    "akool.com": "akool.com",
    "chat.qwen.ai": "chat.qwen.ai",
    "digen.ai": "digen.ai",
    "gemini.google.com": "gemini.google.com",
    "grok.com": "grok.com",
    "www.creen.ai": "creen.ai",
    "www.meta.ai": "meta.ai",
    "www.nemovideo.com": "nemovideo.com",
}

# Read-only DOM probe: look for paywall/credits-exhausted language, a live video or
# spinner, and any visible error toast. Returns a small classification dict.
PROBE_JS = r"""
(() => {
  const txt = (document.body ? document.body.innerText : "").toLowerCase();
  const has = (arr) => arr.filter(w => txt.includes(w));
  const paywall = has(["upgrade", "out of credits", "no credits", "insufficient",
                       "buy credits", "get more credits", "credits remaining: 0",
                       "0 credits", "subscribe", "premium", "paywall", "quota",
                       "limit reached", "exceeded", "免费额度", "积分不足", "升级"]);
  const videoEl = document.querySelectorAll("video").length;
  const spinner = !!document.querySelector(
      "[class*='spin' i],[class*='loading' i],[class*='progress' i],[aria-busy='true']");
  const err = has(["error", "failed", "something went wrong", "try again", "出错", "失败"]);
  // Any media URL already in the DOM?
  let mediaUrl = "";
  const v = document.querySelector("video");
  if (v) { mediaUrl = v.currentSrc || v.src || ""; }
  return {
    url: location.href,
    paywallHits: paywall.slice(0, 4),
    videoEls: videoEl,
    mediaUrl: (mediaUrl || "").slice(0, 80),
    spinner: spinner,
    errHits: err.slice(0, 3),
    bodyLen: txt.length
  };
})()
"""


def find_tab(match):
    for port in (9222, 9223, 9224, 9225):
        try:
            for t in list_targets(port=port):
                if t.get("type") == "page" and match in (t.get("url") or ""):
                    return port, t
        except Exception:
            continue
    return None, None


def main():
    out_lines = []
    for host, match in HOSTS.items():
        port, tab = find_tab(match)
        if not tab:
            out_lines.append(f"{host:22s} NO_TAB (no live tab matching {match!r})")
            continue
        try:
            with Page(match=match, timeout=30, port=port) as pg:
                r = pg.evaluate(PROBE_JS, timeout=40)
            if not isinstance(r, dict):
                out_lines.append(f"{host:22s} PROBE_NONE (evaluate returned {r!r})")
                continue
            # Classify.
            if r.get("paywallHits"):
                state = "ZERO_CREDITS/PAYWALL"
            elif r.get("mediaUrl") or r.get("videoEls", 0) > 0:
                state = "VIDEO_PRESENT"
            elif r.get("spinner"):
                state = "STILL_RENDERING"
            elif r.get("errHits"):
                state = "ERROR_ON_PAGE"
            else:
                state = "IDLE/UNKNOWN"
            detail = (f"pw={r.get('paywallHits')} vid={r.get('videoEls')} "
                      f"media={r.get('mediaUrl')!r} spin={r.get('spinner')} "
                      f"err={r.get('errHits')}")
            out_lines.append(f"{host:22s} :{port} {state:22s} {detail}")
        except Exception as e:
            out_lines.append(f"{host:22s} PROBE_ERR {type(e).__name__}: {str(e)[:90]}")

    report = "\n".join(out_lines)
    print(report)
    pathlib.Path(__file__).parent.joinpath("_video_nojs_probe.txt").write_text(
        report, encoding="utf-8")


if __name__ == "__main__":
    main()
