"""Test the REAL UniversalSessionClient.chat() path for Gemini with prompt injection.

The sweep scored gemini AUTH, but a raw uninjected probe got a real answer.
This isolates whether prompt-injection corrupts the Gemini f.req body.
"""
import sys
sys.path.insert(0, "scripts/automation")
from pathlib import Path
from universal_replay import UniversalSessionClient, ChatError

path = Path("state/secrets/session_google_gemini_web.json")
client = UniversalSessionClient(path)

# Show what injection produces
new_prompt = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
injected = client._inject_prompt(new_prompt)
print("base_body == injected?", injected == client.base_body)
print("sentinel still present?", "Reply%20exactly%20one%20word" in injected)
print("holy cow present (encoded)?", "holy%20cow" in injected or "holy+cow" in injected)

# Now fire the real chat
try:
    res = client.chat([{"role": "user", "content": new_prompt}])
    print("\n=== chat() OK ===")
    print("status:", res.get("status"))
    print("text:", repr(str(res.get("text"))[:300]))
    raw = str(res.get("raw") or "")
    print("raw len:", len(raw))
    print("holy cow in raw?", "the holy cow" in raw.lower())
    print("raw head:", repr(raw[:400]))
except ChatError as e:
    print("\n=== chat() ChatError ===")
    print("args:", e.args)
    print("code:", getattr(e, "code", None))
    raw = getattr(e, "raw", "") or ""
    print("status:", getattr(e, "status", None))
    print("raw len:", len(raw))
    print("raw head:", repr(raw[:500]))
except Exception as e:
    print("\n=== chat() EXC ===", type(e).__name__, e)
