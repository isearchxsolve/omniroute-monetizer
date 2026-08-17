"""Inspect current chatLanguageModels.json structure."""
import json
from pathlib import Path

p = Path.home() / "AppData/Roaming/Code/User/chatLanguageModels.json"
d = json.loads(p.read_text())
print("groups:", len(d))
for g in d:
    url = g["models"][0]["url"] if g.get("models") else None
    print(f"  {g['name']}: {len(g.get('models', []))} models, url={url}")
print("\nsample model entry:")
print(json.dumps(d[1]["models"][0], indent=2))
print("\nsample group keys:", list(d[1].keys()))
