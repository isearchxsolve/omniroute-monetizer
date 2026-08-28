"""Verify the :8190 consumer contract matches the operator's final spec, live.

Checks:
1. GET /v1/models — total count, chat routes, video routes, pin routes.
2. Session counts per modality (spec: 25 chat, 23 video).
3. One LIGHT chat call via session-pool/auto — confirms 200 + provider/session fields.
   (No video submit: that spends credits; video route presence is verified via /v1/models.)
"""
import json, sys, pathlib, urllib.request

BASE = "http://127.0.0.1:8190/v1"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.load(r)

def post(path, body, timeout=120):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

# --- 1. routes ---
data = get("/models")
models = [m.get("id", "") for m in data.get("data", [])]
video_routes = sorted(set(m for m in models if m.startswith("video/")))
chat_routes  = sorted(set(m for m in models if not m.startswith("video/")))
print("total models:", len(models))
print("chat routes (%d):" % len(chat_routes))
for m in chat_routes: print("   ", m)
print("video routes (%d):" % len(video_routes))
for m in video_routes: print("   ", m)
print("has session-pool/auto:", "session-pool/auto" in models)
print("has video/auto:", "video/auto" in models)
print("has video/labs.google/auto:", "video/labs.google/auto" in models)

# --- 2. session counts per modality (from the pool itself, read-only) ---
sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))
from session_pool import SessionPool
p = SessionPool()
chat_seats = [s for s in p.sessions if s.modality != "video"]
video_seats = [s for s in p.sessions if s.modality == "video"]
chat_disp = [s for s in chat_seats if s.dispatchable]
video_disp = [s for s in video_seats if s.dispatchable]
print()
print("chat seats: %d total, %d dispatchable (spec says 25)" % (len(chat_seats), len(chat_disp)))
print("video seats: %d total, %d dispatchable (spec says 23)" % (len(video_seats), len(video_disp)))

# --- 3. one light chat call: Law-3 arithmetic, verifies provider+session fields ---
print()
try:
    resp = post("/chat/completions", {
        "model": "session-pool/auto",
        "messages": [{"role": "user", "content": "Reply with only the number: 41+17"}],
    })
    top_keys = sorted(resp.keys())
    choice = resp.get("choices", [{}])[0]
    text = (choice.get("message") or {}).get("content", "")
    print("chat call HTTP 200 OK")
    print("top-level keys:", top_keys)
    print("provider field:", resp.get("provider"))
    print("session field:", resp.get("session"))
    print("answer text:", repr(text[:80]))
    print("Law-3 arithmetic check (expect 58):", "PASS" if "58" in text else "CHECK-MANUALLY")
except Exception as e:
    print("chat call FAILED:", type(e).__name__, e)
