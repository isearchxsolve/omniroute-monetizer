# Sweep EVERY automation Chrome instance (all debug ports) for video-capable tabs.
# The :9222 scan found 5 candidates, but the video_accounts registry lists ports
# 9222-9225 (flow seats on 9223/9224/9225). "Hidden" engines may live on the other
# profiles. Read-only: GET /json only, never drives anything.
import json
import urllib.request

PORTS = (9222, 9223, 9224, 9225, 9226, 9227, 9228, 9229, 9230)

VIDEO_TOKENS = (
    "flow", "veo", "video", "labs.google", "veoaifree", "digen", "rtst", "kie",
    "runway", "pika", "kling", "hailuo", "luma", "genmo", "haiper", "invideo",
    "synthesia", "heygen", "akool", "creen", "minimax", "pixverse", "viggle",
    "seedance", "firefly", "adobe", "nemo", "vidu", "wan", "mochi", "cogvideo",
    "dreamina", "jimeng", "higgsfield", "freepik", "rendernet", "pollo", "vmake",
    "neural", "deepbrain", "d-id", "colossyan", "fliki", "pictory", "invideo",
)

def is_video(t):
    blob = (t.get("url", "") + " " + t.get("title", "")).lower()
    return any(tok in blob for tok in VIDEO_TOKENS)

total_video = 0
for port in PORTS:
    try:
        raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=4).read()
        tabs = json.loads(raw)
    except Exception as e:
        print(f":{port}  NO_BROWSER ({type(e).__name__})")
        continue
    pages = [t for t in tabs if t.get("type") == "page"]
    vids = [t for t in pages if is_video(t)]
    total_video += len(vids)
    print(f"\n:{port}  {len(pages)} open pages, {len(vids)} video-capable")
    for t in vids:
        print(f"   VIDEO  {t.get('url','')[:95]}")
        print(f"          title: {(t.get('title') or '')[:70]}")
    for t in pages:
        if not is_video(t):
            print(f"   other  {t.get('url','')[:95]}")

print(f"\nTOTAL video-capable tabs across all ports: {total_video}")
