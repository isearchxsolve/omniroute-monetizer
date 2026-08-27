"""Enumerate video-capable tabs from all rescan result files."""
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE = pathlib.Path(__file__).resolve().parent / "state"

VIDEO_HINTS = ("video", "flow", "heygen", "akool", "creen", "digen", "veo", "rtst",
               "giz", "magichour", "pika", "kling", "runway", "luma", "haiper",
               "labs.google", "nemo", "vidu", "hailuo", "minimax", "pixverse",
               "invideo", "synthesia", "colossyan", "deepbrain", "hourone",
               "genmo", "stablevideo", "animate", "film", "studio")

total_tabs = 0
video_tabs = []

for f in sorted(STATE.glob("rescan_*.json")):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{f.name}: ERROR {e}")
        continue
    total_tabs += len(data)
    print(f"\n=== {f.name}: {len(data)} tabs ===")
    for t in data:
        url = t.get("url", "")
        title = t.get("title", "")
        port = t.get("port", "?")
        status = t.get("status", t.get("live", "?"))
        host = url.split("/")[2] if "://" in url else url
        is_video = any(h in url.lower() or h in host.lower() or h in title.lower()
                       for h in VIDEO_HINTS)
        markers = []
        for k in ("avatars", "gen", "credits", "signed_in", "wall", "auth"):
            if k in t:
                markers.append(f"{k}={t[k]}")
        tag = "VIDEO" if is_video else "     "
        print(f"  [{tag}] port={port} status={status} {host} | {title[:60]} | {' '.join(markers)}")
        if is_video:
            video_tabs.append((port, host, title, status, dict(t)))

print(f"\n{'='*60}")
print(f"TOTAL TABS: {total_tabs}")
print(f"VIDEO-CAPABLE TABS: {len(video_tabs)}")
print(f"\nVideo hosts discovered:")
seen = set()
for port, host, title, status, t in video_tabs:
    key = (port, host)
    if key not in seen:
        seen.add(key)
        print(f"  :{port} {host} — {title[:70]} (status={status})")
