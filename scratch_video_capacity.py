"""scratch_video_capacity.py -- honest dispatchable video seat inventory + clip estimate."""
import sys
sys.path.insert(0, "scripts/automation")
from session_pool import SessionPool

p = SessionPool()
vs = [s for s in p.sessions if s.modality == "video"]
print("video seats:", len(vs))
print("dispatchable:", sum(1 for s in vs if s.dispatchable))
print()
for s in vs:
    rec = getattr(s, "has_recording", None)
    api = getattr(s, "has_api", None)
    chrome = getattr(s, "has_chrome", None)
    vchrome = getattr(s, "has_video_chrome", None)
    print(f"{s.host:26s} disp={s.dispatchable!s:5s} rec={rec!s:5s} api={api!s:5s} "
          f"chrome={chrome!s:5s} vchrome={vchrome!s:5s} reason={s.reason}")
