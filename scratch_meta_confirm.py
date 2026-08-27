import sys, pathlib, json
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient

p = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_meta_ai_web.json")
c = UniversalSessionClient(p)
out = c.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
text = out.get("text", "")
print("len:", len(text))
print("head:", text[:300])
# Is it a JSON envelope (not an answer)?
try:
    obj = json.loads(text)
    print("\nPARSES AS JSON -> envelope, NOT a model answer.")
    print("top keys:", list(obj.keys()) if isinstance(obj, dict) else type(obj))
    data = obj.get("data", {}) if isinstance(obj, dict) else {}
    print("data keys:", list(data.keys()) if isinstance(data, dict) else data)
except Exception:
    print("\nnot JSON -> could be a real answer")
# Does it contain the word Omni as an answer?
print("\ncontains 'Omni'?", "Omni" in text)
