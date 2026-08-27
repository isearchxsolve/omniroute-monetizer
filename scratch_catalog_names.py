"""Dump the exact site-catalog names the capture tool uses, so we can build a forced --sites list."""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SITES_FILE = ROOT / "state/free_llm_chat_sites.json"

out = {"veoaifree": "https://veoaifree.com/", "rtst.ai": "https://rtst.ai/",
       "digen.ai": "https://digen.ai/",
       "Google Flow (labs.google)": "https://labs.google/fx/tools/flow"}
for g in json.loads(SITES_FILE.read_text(encoding="utf-8")):
    for s in g.get("sites") or []:
        if s.get("url"):
            out[s.get("name") or s["url"]] = s["url"]

print("catalog names:", len(out))
for n in sorted(out):
    print(" ", repr(n), "->", out[n])

# which already have session files
def slug(name):
    return name.replace(" ", "_").replace("/", "_").replace(".", "_").lower()
secrets = ROOT / "state/secrets"
done = {p.stem for p in secrets.glob("session_*.json")}
print("\n--- catalog names WITHOUT a session file (fresh) ---")
for n in sorted(out):
    if f"session_{slug(n)}" not in done:
        print(" ", repr(n))
