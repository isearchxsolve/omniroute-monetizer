# Ground truth for the Chrome Gap Doctrine: what tabs are ACTUALLY open in the :9222
# automation browser, and which of them are video-generation surfaces. This is the
# "shallow investigation first" step -- enumerate the live supply before deciding what
# to wire. Read-only: only GET /json, never drives anything.
import json
import urllib.request

PORT = 9222
try:
    raw = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=10).read()
    tabs = json.loads(raw)
except Exception as e:
    print(f"NO_BROWSER on :{PORT}: {e}")
    raise SystemExit(1)

pages = [t for t in tabs if t.get("type") == "page"]
print(f"open pages on :{PORT}: {len(pages)}\n")

# Heuristic video-surface tokens. A tab whose URL/title matches one of these is a
# CANDIDATE video host -- the doctrine then asks "can a human generate here, and what
# send-time field does Chrome add that my replay misses?"
VIDEO_TOKENS = (
    "flow", "veo", "video", "labs.google", "veoaifree", "digen", "rtst", "kie",
    "runway", "pika", "kling", "hailuo", "luma", "genmo", "haiper", "invideo",
    "synthesia", "heygen", "akool", "creen", "digen", "minimax", "hailuo",
    "pixverse", "viggle", "seedance", "firefly", "adobe",
)

def is_video(t):
    blob = (t.get("url", "") + " " + t.get("title", "")).lower()
    return any(tok in blob for tok in VIDEO_TOKENS)

print("=== VIDEO-CAPABLE candidate tabs ===")
n = 0
for t in pages:
    if is_video(t):
        n += 1
        print(f"  [{n}] {t.get('url','')[:90]}")
        print(f"       title: {(t.get('title') or '')[:70]}")
if not n:
    print("  (none matched the heuristic tokens)")

print("\n=== ALL other tabs (for context) ===")
for t in pages:
    if not is_video(t):
        print(f"  {t.get('url','')[:95]}")
