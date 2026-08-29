import json, pathlib, sys
sys.path.insert(0, 'D:/omniroute-monetizer/scripts/automation')
sys.path.insert(0, 'D:/omniroute-monetizer/scripts/automation/adapters')

from universal_replay import UniversalSessionClient

session_file = pathlib.Path("state/secrets/session_deepseek_chat.json")
session = json.loads(session_file.read_text(encoding="utf-8"))

client = UniversalSessionClient(session)

print("Sending chat request...")
try:
    result = client.chat([{"role": "user", "content": "Reply exactly one word: Omni"}])
    print("SUCCESS!")
    print("Text:", result.get("text", ""))
    print("Label:", result.get("label", ""))
except Exception as e:
    print("FAILED:", type(e).__name__, str(e))
    if hasattr(e, 'raw'):
        print("RAW BODY (first 1000):", str(e.raw)[:1000])
