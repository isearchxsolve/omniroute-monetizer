"""Single-seat live proof: serve ONE chat via stateless HTTP replay (no Chrome).
Instantiates UniversalSessionClient directly on the api.groq.com seat file and
sends one benign prompt. Proves the runtime path works WITHOUT a live browser.
Costs exactly one provider call."""
import sys, json, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SECRETS = pathlib.Path("state/secrets")
# find the groq seat file
cands = list(SECRETS.glob("session_*groq*.json"))
print("candidate seat files:", [c.name for c in cands])
if not cands:
    print("NO groq seat file found"); sys.exit(1)
seat = cands[0]
print("using:", seat.name)

from universal_replay import UniversalSessionClient
t0 = time.time()
try:
    client = UniversalSessionClient(str(seat))
    print("client built OK; url =", client.url)
    result = client.chat([{"role": "user", "content": "Reply with the single word: ready"}],
                         model="groq-test")
    dt = time.time() - t0
    text = result.get("text", "") if isinstance(result, dict) else str(result)
    print(f"\nLIVE REPLY in {dt:.1f}s (NO Chrome in path):")
    print("  ", text[:300])
    print("\nRESULT: STATELESS REPLAY WORKS" if text.strip() else "RESULT: empty reply")
except Exception as e:
    dt = time.time() - t0
    print(f"\nFAILED after {dt:.1f}s: {type(e).__name__}: {e}")
