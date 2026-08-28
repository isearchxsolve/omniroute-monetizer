"""Submit a video-explicit prompt to grok (worklog #1123).

Operator confirmed: grok has NO video mode toggle — video is triggered by the PROMPT itself.
So the prompt must explicitly ask for a video. Dispatch the grok VIDEO seat through the pool.
"""
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

os.environ.setdefault("OMNI_VIDEO_CONFIRM_SPEND", "1")

from session_pool import SessionPool, SECRETS  # noqa: E402

# Video-explicit prompt for grok (prompt-driven video, no mode toggle)
PROMPT = ("Generate a video: a red ball rolling slowly across a bright white studio floor, "
          "smooth camera tracking shot, soft lighting")

pool = SessionPool(SECRETS)
lines = []
ran = False
for s in pool.sessions:
    if s.host != "grok.com" or s.modality != "video":
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
        lines.append(f"{s.host} LIVE  {dt:6.1f}s  url={url[:140]}  label={r.get('label')}")
    except Exception as e:
        dt = time.time() - t0
        lines.append(f"{s.host} FAIL  {dt:6.1f}s  {type(e).__name__}: {str(e)[:140]}")
    break

if not ran:
    lines.append("no dispatchable grok video seat found")
report = "\n".join(lines)
print(report)
ROOT.joinpath("_grok_submit.txt").write_text(report, encoding="utf-8")
