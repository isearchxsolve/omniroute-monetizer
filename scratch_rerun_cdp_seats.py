"""Re-run the 3 CDP-transport-timeout video seats (heygen/magichour/giz) through the
SAME pool dispatch path the sweep uses, now that _gen_ui's inject/snap/click evaluates
carry a 120s timeout instead of the 45s default (worklog #1123).

Operator-consented real generations (video sweep). These are UI-driven seats, so no
rtst spend gate applies; the site's own UI burns its own credits.
"""
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

os.environ.setdefault("OMNI_VIDEO_CONFIRM_SPEND", "1")

from session_pool import SessionPool, SECRETS  # noqa: E402

PROMPT = ("a red ball rolling slowly across a bright white studio floor, "
          "smooth camera tracking shot, soft lighting")

pool = SessionPool(SECRETS)
targets = ("heygen", "magichour", "giz")

lines = []
for s in pool.sessions:
    if not any(t in s.host for t in targets):
        continue
    if not s.dispatchable:
        lines.append(f"{s.host:20s} SKIP not dispatchable: {s.reason}")
        continue
    t0 = time.time()
    try:
        r = s.chat([{"role": "user", "content": PROMPT}])
        dt = time.time() - t0
        url = r.get("video_url") or r.get("text") or ""
        lines.append(f"{s.host:20s} LIVE  {dt:6.1f}s  url={url[:100]}  label={r.get('label')}")
    except Exception as e:
        dt = time.time() - t0
        lines.append(f"{s.host:20s} FAIL  {dt:6.1f}s  {type(e).__name__}: {str(e)[:120]}")

report = "\n".join(lines)
print(report)
ROOT.joinpath("_video_cdp_rerun.txt").write_text(report, encoding="utf-8")
