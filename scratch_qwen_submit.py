"""Check qwen video-mode state, then submit the video prompt (worklog #1123).

Operator selected the video option on qwen. Verify composer state, then dispatch the
qwen VIDEO seat through the pool (fixed inject: select-all-replace; fixed CDP: wake tab).
"""
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

os.environ.setdefault("OMNI_VIDEO_CONFIRM_SPEND", "1")

from cdp import Page, list_targets  # noqa: E402
from session_pool import SessionPool, SECRETS  # noqa: E402

PROMPT = ("a red ball rolling slowly across a bright white studio floor, "
          "smooth camera tracking shot, soft lighting")

lines = []

# --- state check first ---
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
            r = pg.evaluate(r"""
(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const input = Array.from(document.querySelectorAll("textarea,[contenteditable='true']")).find(vis);
  const out = {url: location.href};
  out.composer = input ? (input.tagName + " val=" + JSON.stringify((input.value || input.innerText || "").slice(0, 60))) : "NONE";
  out.videoish = [];
  document.querySelectorAll("button,[role='button'],[role='tab'],[role='menuitem'],[role='menuitemcheckbox'],a").forEach(el => {
    if (!vis(el)) return;
    const lbl = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).replace(/\s+/g, " ").trim();
    if (/video|wan|create|generat|media/i.test(lbl)) out.videoish.push({tag: el.tagName, lbl: lbl.slice(0, 50), checked: el.getAttribute("aria-checked")});
  });
  out.videoish = out.videoish.slice(0, 12);
  const txt = (document.body ? document.body.innerText : "");
  out.tail = txt.replace(/\n+/g, " | ").slice(-200);
  return out;
})()
""", timeout=30)
        lines.append(f"qwen state url: {r.get('url')}")
        lines.append(f"qwen composer: {r.get('composer')}")
        lines.append(f"qwen videoish: {r.get('videoish')}")
        lines.append(f"qwen tail: {r.get('tail')!r}")
    except Exception as e:
        lines.append(f"qwen state ERR {type(e).__name__}: {str(e)[:90]}")
else:
    lines.append("qwen: NO_TAB")

# --- submit through pool ---
pool = SessionPool(SECRETS)
ran = False
for s in pool.sessions:
    if s.host != "chat.qwen.ai" or s.modality != "video":
        continue
    if not s.dispatchable:
        lines.append(f"{s.host} SKIP not dispatchable: {s.reason}")
        continue
    ran = True
    t0 = time.time()
    try:
        r = s.chat([{"role": "user", "content": PROMPT}])
        dt = time.time() - t0
        url = r.get("video_url") or r.get("text") or ""
        lines.append(f"{s.host} LIVE  {dt:6.1f}s  url={url[:120]}  label={r.get('label')}")
    except Exception as e:
        dt = time.time() - t0
        lines.append(f"{s.host} FAIL  {dt:6.1f}s  {type(e).__name__}: {str(e)[:140]}")
    break

if not ran:
    lines.append("no dispatchable qwen video seat found")
report = "\n".join(lines)
print(report)
ROOT.joinpath("_qwen_submit.txt").write_text(report, encoding="utf-8")
