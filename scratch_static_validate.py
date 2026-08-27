"""Zero-cost static validation of the 14 graduation candidates.
For each Chrome-backed seat WITH a recorded_exchange, check the blueprint is
complete enough for stateless replay: url, method, request_body, and a cookie
(either cookie_header or a Cookie request header). No provider calls."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from session_pool import SessionPool

pool = SessionPool()
ready, blocked = [], []
for s in pool.sessions:
    if not s.dispatchable or not (s.has_chrome or s.has_video_chrome):
        continue
    if not s.has_recording:
        continue
    try:
        raw = json.loads(s.path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        blocked.append((s.host, s.modality, f"parse error: {e}"))
        continue
    ex = raw.get("recorded_exchange") or {}
    url = ex.get("url")
    method = ex.get("method", "POST")
    body = ex.get("request_body")
    hdrs = ex.get("request_headers") or {}
    has_cookie = "cookie_header" in raw or any(k.lower() == "cookie" for k in hdrs)
    problems = []
    if not url:
        problems.append("no url")
    if body in (None, ""):
        problems.append("no body")
    if not has_cookie:
        problems.append("NO COOKIE")
    if problems:
        blocked.append((s.host, s.modality, ", ".join(problems)))
    else:
        ready.append((s.host, s.modality, method, url))

print(f"READY for stateless replay ({len(ready)}):")
for h, m, meth, u in sorted(ready):
    print(f"   {m:5} {h:24} {meth:5} {u[:52]}")
print(f"\nBLOCKED ({len(blocked)}):")
for h, m, why in sorted(blocked):
    print(f"   {m:5} {h:24} {why}")
