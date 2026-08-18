"""Verify the pure Chrome on CDP 9223: which tabs are open + is Google signed in."""
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:9223/json/version", timeout=5) as r:
    v = json.loads(r.read())
print("Browser:", v.get("Browser"))

with urllib.request.urlopen("http://127.0.0.1:9223/json", timeout=5) as r:
    tabs = json.loads(r.read())
pages = [t for t in tabs if t.get("type") == "page"]
print(f"Open tabs: {len(pages)}")
for t in pages:
    print("  TAB:", t.get("url", "")[:90])
