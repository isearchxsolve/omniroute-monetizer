"""Re-run the 3 unresolved NO_VIDEO seats (gemini/grok/qwen) through the pool dispatch
path now that Page() wakes frozen tabs (worklog #1123).

grok's earlier failure was literally "Document is not focused" (the freeze bug);
qwen's prompt never landed (promptSeen False, likely frozen). Both should now inject.
gemini was still rendering — may have finished.
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
# gemini is ALREADY rendering (the killed run injected+clicked before stop); recover its
# video by polling instead of re-submitting (which would duplicate again). Only grok and
# qwen get a fresh submit here, now with the select-all-replace inject fix.
targets = ("grok.com", "chat.qwen.ai")

lines = []
for s in pool.sessions:
    if s.host not in targets:
        continue
    if s.modality != "video":
        lines.append(f"{s.host:20s} SKIP modality={s.modality} (chat seat, not video)")
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
        lines.append(f"{s.host:20s} FAIL  {dt:6.1f}s  {type(e).__name__}: {str(e)[:140]}")

report = "\n".join(lines)
print(report)
ROOT.joinpath("_video_nojs_rerun.txt").write_text(report, encoding="utf-8")
