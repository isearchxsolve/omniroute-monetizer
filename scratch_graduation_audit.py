"""Zero-cost graduation audit: which Chrome-backed seats already carry a
recorded_exchange (i.e. can be served by stateless HTTP replay instead of a
live Chrome tab). Reads seat files only; makes NO provider calls."""
import sys, json, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from session_pool import SessionPool

pool = SessionPool()
now = time.time()
hdr = f"{'host':24} {'mod':5} {'cookie':6} {'alive':8} {'age_d':6} endpoint"
print(hdr)
print("-" * len(hdr))
grad, norec = [], []
for s in pool.sessions:
    if not s.dispatchable:
        continue
    if not (s.has_chrome or s.has_video_chrome):
        continue
    if not s.has_recording:
        norec.append((s.host, s.modality))
        continue
    try:
        raw = json.loads(s.path.read_text(encoding="utf-8-sig"))
    except Exception:
        continue
    ex = raw.get("recorded_exchange") or {}
    hdrs = ex.get("request_headers") or {}
    has_cookie = "cookie_header" in raw or any(k.lower() == "cookie" for k in hdrs)
    st = raw.get("status") or {}
    ts = st.get("checked_at") or st.get("ts") or 0
    age = f"{(now - ts) / 86400:.0f}" if ts else "?"
    print(f"{s.host:24} {s.modality:5} {('y' if has_cookie else 'NO'):6} "
          f"{str(st.get('alive')):8} {age:6} {str(ex.get('url', ''))[:48]}")
    grad.append((s.host, s.modality))

print()
print(f"graduation candidates (have recorded_exchange): {len(grad)}")
print(f"chrome-only, need capture first:                {len(norec)}")
for h, m in sorted(norec):
    print(f"   conly {m:5} {h}")
