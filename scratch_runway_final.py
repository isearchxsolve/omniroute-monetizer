"""Final runway verdict for two 3-min films (72 clips).

Read-only: uses each seat client's free capacity() read. ZERO spend.
Applies TECHNOLOGY_TRANSFER §23: only counts supply that does NOT need Chrome
(file-backed replay + API-credential seats), because serving the pool never
requires Chrome — Chrome is only needed to update/expand the pool.
"""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))

from session_pool import SessionPool

NEEDED = 72  # 2 films x 36 clips (3 min = 180s / 5s per clip)

p = SessionPool()
vids = [s for s in p.sessions if s.modality == "video"]

chrome_free_clips = 0
chrome_backed = 0
rows = []
for s in vids:
    cls = s.client_cls.__name__ if s.client_cls else "None"
    # Chrome-free tiers per §23: API-credential seats + file-backed replay.
    api = bool(getattr(s, "has_api", False))
    rec = bool(getattr(s, "has_recording", False))
    chrome = bool(getattr(s, "has_chrome", False)) or bool(getattr(s, "has_video_chrome", False))
    tier = "API" if api else ("REPLAY" if rec else ("CHROME" if chrome else "?"))

    clips = None
    if api and s.dispatchable:
        # Free capacity read for API seats (rtst, flow). Pool contract: client_cls(secret=<path>).
        try:
            c = s.client_cls(secret=s.path)
            cap = c.capacity()
            clips = int(cap.get("clipsRemaining", 0))
        except Exception as e:
            clips = f"ERR:{type(e).__name__}:{e}"
    if isinstance(clips, int):
        chrome_free_clips += clips
    if tier == "CHROME":
        chrome_backed += 1
    rows.append((s.key, tier, cls, s.dispatchable, clips))

print("=== RUNWAY VERDICT: two 3-min films = %d clips needed ===" % NEEDED)
print()
print("%-34s %-7s %-22s %-6s %s" % ("seat", "tier", "client", "disp", "clips"))
for key, tier, cls, disp, clips in rows:
    print("%-34s %-7s %-22s %-6s %s" % (key, tier, cls, str(disp), clips))
print()
print("Chrome-FREE verified clips (API seats, live balance): %d" % chrome_free_clips)
print("Chrome-backed seats (need live tab, NOT counted):      %d" % chrome_backed)
print()
if chrome_free_clips >= NEEDED:
    print("VERDICT: GO — %d Chrome-free clips >= %d needed. Runway clear WITHOUT Chrome." % (chrome_free_clips, NEEDED))
else:
    print("VERDICT: SHORTFALL — %d Chrome-free clips < %d needed (gap %d)." % (chrome_free_clips, NEEDED, NEEDED - chrome_free_clips))
