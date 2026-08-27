"""scratch_pool_grok.py — force-route ONE call to the grok ws seat through the pool."""
import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from session_pool import SessionPool

pool = SessionPool()
live = pool.live(host="grok.com")
print("live grok sessions:", [(s.key, s.modality, s.client_cls.__name__ if s.client_cls else None) for s in live])

r = pool.chat([{"role": "user", "content": "Reply exactly one word: Omni."}], host="grok.com")
print("\nprovider:", r.get("provider"))
print("session :", r.get("session"))
print("label   :", r.get("label"))
print("status  :", r.get("status"))
print("text    :", r.get("text"))
