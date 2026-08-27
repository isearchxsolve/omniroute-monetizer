"""scratch_pool_grok_ws.py — call the grok WS seat directly through the pool object."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from session_pool import SessionPool

pool = SessionPool()
ws_seat = next((s for s in pool.sessions if s.key == "session_grok_ws"), None)
print("ws seat:", ws_seat.key if ws_seat else None,
      "| client:", ws_seat.client_cls.__name__ if ws_seat and ws_seat.client_cls else None,
      "| dispatchable:", ws_seat.dispatchable if ws_seat else None)

r = ws_seat.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
print("\nlabel :", r.get("label"))
print("status:", r.get("status"))
print("text  :", r.get("text"))
print("ms    :", (r.get("raw") or {}).get("ms"))
print("\nRESULT:", "GROK-WS-GRADUATED-CHROME-FREE" if r.get("text") == "Omni" else "FAIL")
