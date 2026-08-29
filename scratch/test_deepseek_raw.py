import json, pathlib, sys
sys.path.insert(0, 'D:/omniroute-monetizer/scripts/automation')
sys.path.insert(0, 'D:/omniroute-monetizer/scripts/automation/adapters')

from universal_replay import UniversalSessionClient

session_file = pathlib.Path("state/secrets/session_deepseek_chat.json")
session = json.loads(session_file.read_text(encoding="utf-8"))

client = UniversalSessionClient(session)

# Patch the chat method to dump the raw body after PoW
import universal_replay as ur

original_fire = client._fire
def patched_fire(method, url, headers, body, timeout):
    r = original_fire(method, url, headers, body, timeout)
    if "chat.deepseek.com/api/v0/chat/completion" in (url or ""):
        print("=== RAW BODY (first 2000) ===")
        print(r.text[:2000])
        print("=== END RAW BODY ===")
    return r
client._fire = patched_fire

print("Sending chat request...")
try:
    result = client.chat([{"role": "user", "content": "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"}])
    print("SUCCESS!")
    print("Text:", result.get("text", "")[:200])
except Exception as e:
    print("FAILED:", type(e).__name__, str(e)[:300])
    if hasattr(e, 'raw'):
        print("RAW BODY:", str(e.raw)[:2000])
