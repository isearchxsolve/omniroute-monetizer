import json, sys, time
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

# gemini with a REAL prompt (not the sentinel)
g = UniversalSessionClient(str(SEATDIR / "session_google_gemini_web.json"))
t0 = time.time()
try:
    resp = g.chat([{"role": "user", "content": "What is 2+2? Answer with just the number."}])
    dt = time.time() - t0
    text = resp.get("content") or resp.get("text") or json.dumps(resp)[:300] if isinstance(resp, dict) else str(resp)
    print(f"GEMINI: LIVE ({dt:.1f}s) -> {str(text)[:200]!r}")
except Exception as e:
    dt = time.time() - t0
    print(f"GEMINI: ERROR ({dt:.1f}s) -> {str(e)[:300]!r}")
