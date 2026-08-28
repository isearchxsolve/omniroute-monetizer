"""Honest runway capacity for 2x 3-min films. FREE reads only — never spends a credit.

Checks:
  1. All 4 rtst API seats: balance + clips affordable (free /user/credits + /video/estimate-credits).
  2. Every dispatchable video seat in the pool: host, dispatch path, reason.
Writes _runway_capacity.txt.
"""
import os, sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))

OUT = pathlib.Path(__file__).resolve().parent / "_runway_capacity.txt"
lines = []
def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)

# ---- 1. rtst seats: free balance reads ----------------------------------------------------------
p("=== RTST API SEATS (free reads) ===")
SECRETS = pathlib.Path(__file__).resolve().parent / "state" / "secrets"
rtst_files = sorted(SECRETS.glob("session_rtst_ai*.json"))
rtst_total_clips = 0
try:
    from rtst_api_client import RtstApiClient, ChatError, SessionExpired
    for f in rtst_files:
        try:
            c = RtstApiClient(secret=f)
            bal = c.credits()
            # cheapest clip cost
            cheapest = None
            try:
                cap = c.capacity()
                cheapest = cap.get("cheapest") or {}
                clips = int(cap.get("clipsRemaining") or 0)
            except Exception as e:
                clips = 0
                cheapest = {"err": str(e)[:60]}
            rtst_total_clips += clips
            p(f"  {f.name:34s} credits={bal:<7.1f} clips_affordable={clips:<3} cheapest={cheapest}")
        except SessionExpired as e:
            p(f"  {f.name:34s} AUTH-DEAD: {str(e)[:80]}")
        except ChatError as e:
            p(f"  {f.name:34s} ERROR: {str(e)[:80]}")
        except Exception as e:
            p(f"  {f.name:34s} FAIL: {type(e).__name__} {str(e)[:80]}")
    p(f"  RTST TOTAL CLIPS AFFORDABLE: {rtst_total_clips}")
except Exception as e:
    p(f"  rtst module fail: {type(e).__name__} {e}")

# ---- 2. full video seat dispatch map ------------------------------------------------------------
p("")
p("=== ALL VIDEO SEATS (dispatch map) ===")
try:
    from session_pool import SessionPool
    pool = SessionPool()
    vseats = [s for s in pool.sessions if s.modality == "video"]
    p(f"video seats: {len(vseats)}  dispatchable: {sum(1 for s in vseats if s.dispatchable)}")
    p("")
    for s in sorted(vseats, key=lambda x: x.host):
        path = "api" if s.has_api else ("replay" if s.has_recording else ("vchrome" if s.has_video_chrome else ("chrome" if s.has_chrome else "NONE")))
        p(f"  {s.host:26s} disp={str(s.dispatchable):5s} path={path:7s} reason={s.reason}")
except Exception as e:
    p(f"  pool fail: {type(e).__name__} {e}")

OUT.write_text("\n".join(lines), encoding="utf-8")
p(f"\nwrote {OUT}")
