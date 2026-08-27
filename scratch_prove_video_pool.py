"""Confirm video pool dispatch + fall-through mechanics (worklog #1109)."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import session_pool as sp
from veoaifree_chat_client import ChatError

pool = sp.SessionPool()
vid = pool.live(modality="video")
chat = pool.live(modality="chat")
print(f"live VIDEO sessions: {len(vid)}")
print(f"live CHAT  sessions: {len(chat)}")
print("\nvideo sessions + client class:")
for s in sorted(vid, key=lambda x: x.last_used):
    print(f"  {s.host:24s} {s.key:34s} client={s.client_cls.__name__ if s.client_cls else None}")

# Prove video fall-through with stubs (no network).
if len(vid) >= 2:
    calls = []
    class Stub:
        def __init__(self, i, h): self.i, self.h = i, h
        def chat(self, messages, model=None, **kw):
            calls.append(self.h)
            if self.i == 0:
                raise ChatError("WALL", "allowance exhausted")
            return {"text": "", "label": self.h, "video_url": f"https://x/{self.h}.mp4", "modality": "video"}
    now = time.time()
    for s in pool.sessions:
        s.cooldown_until = 0.0; s.dead = False
    order = sorted(pool.live(modality="video"), key=lambda s: s.last_used)
    order[0]._client = Stub(0, order[0].host)
    order[1]._client = Stub(1, order[1].host)
    try:
        r = pool.chat([{"role":"user","content":"a cube"}], modality="video")
        print(f"\nVIDEO FALL-THROUGH: winner={r.get('provider')} attempted={calls} url={r.get('video_url')}")
        print("VERDICT:", "VIDEO_FALLTHROUGH_WORKS" if len(calls) == 2 else "UNEXPECTED")
    except ChatError as e:
        print(f"\nVIDEO FAILED: {e} attempted={calls}")
