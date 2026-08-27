"""Revert runtime=replay on cerebras + gemini (stateless replay gated by send-time
/ state gaps), keep the refreshed credentials for future attempts. groq stays
graduated (proven LIVE). Keeps the pool dispatching only proven-LIVE seats
stateless; cerebras/gemini fall back to Chrome (live signed-in tabs work)."""
import json, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

for name in ["session_cerebras_inference_chat.json", "session_google_gemini_web.json"]:
    p = SEATDIR / name
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    had = d.pop("runtime", None)
    d["updated_at"] = int(time.time())
    d.setdefault("status", {})["replay_graduation"] = "reverted_send_time_gate"
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"  {name}: runtime flag removed (was {had!r}); refreshed creds kept")

# confirm groq still graduated
g = json.loads((SEATDIR / "session_groq_chat.json").read_text(encoding="utf-8-sig"))
print(f"  session_groq_chat.json: runtime={g.get('runtime')!r} (kept)")
