"""List live CDP tabs on seat1 (port 9222) so we can pick the DeepSeek tab."""
import json, urllib.request

PORT = 9222
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
        tabs = json.loads(r.read().decode())
except Exception as e:
    print("NO_BROWSER on", PORT, "->", e)
    raise SystemExit(1)

pages = [t for t in tabs if t.get("type") == "page"]
print(f"{len(pages)} page tabs on :{PORT}\n")
for t in pages:
    print(f"  {t.get('title','')[:48]:48s} {t.get('url','')[:70]}")
    print(f"      ws: {t.get('webSocketDebuggerUrl','')}")
