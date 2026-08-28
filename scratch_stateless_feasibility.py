"""READ-ONLY enquiry: for each of the 33 chrome-backed seats, what would it take to reach
a stateless (23-style) state? Classifies feasibility WITHOUT touching anything.

Classes:
  A. HAS RECORDING  -> stateless candidate IF the send-time gap is bridgeable
                       (re-capture / multistep follow-up / fresh PoW etc.)
  B. HAS API CREDS  -> could become an API-credential seat (like rtst/flow/you.com)
  C. LIVE-TAB ONLY  -> no bytes at all; needs a capture pass first
"""
import io, json, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))

from session_pool import SessionPool
from chrome_replay_client import ChromeReplayClient
from chrome_video_client import ChromeVideoClient

p = SessionPool()
rows = []
for s in sorted(p.sessions, key=lambda x: (x.modality, x.key)):
    cls = s.client_cls.__name__ if s.client_cls else "None"
    if cls not in ("ChromeReplayClient", "ChromeVideoClient"):
        continue
    raw = json.loads(s.path.read_text(encoding="utf-8-sig"))
    has_rec = bool(raw.get("recorded_exchange") or raw.get("recorded_job"))
    has_api = bool(raw.get("api"))
    grad = (raw.get("status") or {}).get("replay_graduation", "")
    if has_rec:
        feas = "A-HAS-RECORDING"
    elif has_api:
        feas = "B-HAS-API-CREDS"
    else:
        feas = "C-LIVE-TAB-ONLY"
    rows.append((s.key, s.modality, cls, feas, grad))

print("%-36s %-6s %-20s %-18s %s" % ("seat", "modal", "client", "feasibility", "grad-note"))
for key, mod, cls, feas, grad in rows:
    print("%-36s %-6s %-20s %-18s %s" % (key, mod, cls, feas, grad))

from collections import Counter
c = Counter(r[3] for r in rows)
print()
print("TOTAL chrome-backed:", len(rows))
for k in sorted(c):
    print("  %-18s %d" % (k, c[k]))
print()
print("By modality:")
for mod in ("chat", "video"):
    sub = [r for r in rows if r[1] == mod]
    cc = Counter(r[3] for r in sub)
    print("  %-6s %d seats: %s" % (mod, len(sub), dict(cc)))
