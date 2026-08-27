import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(r"d:\omniroute-monetizer\scripts\automation")))
import session_pool as sp

# Verify _client_for returns ChromeVideoClient for video-modality seats
tests = [
    ("veoaifree.com", {"modality": "video"}),
    ("labs.google", {"modality": "video"}),
    ("akool.com", {"modality": "video"}),
    ("grok.com", {"modality": "video"}),      # dual-modal -> video path
    ("grok.com", {"modality": "chat"}),       # dual-modal -> chat path (ChromeReplayClient)
    ("gemini.google.com", {"modality": "video"}),
]
for host, raw in tests:
    cls = sp._client_for(host, raw)
    print(f"  {host:24s} modality={raw['modality']:6s} -> {cls.__name__ if cls else None}")

# Count dispatchable video seats in the pool
pool = sp.SessionPool()
vid = [s for s in pool.sessions if s.modality == "video" and s.dispatchable]
print(f"\nDispatchable VIDEO seats: {len(vid)}")
for s in sorted(vid, key=lambda x: x.host):
    print(f"  {s.host:24s} client={s.client_cls.__name__ if s.client_cls else None} "
          f"port={getattr(s, 'chrome_port', '?')}")
