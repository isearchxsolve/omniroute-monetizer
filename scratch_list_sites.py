"""List directory sites + existing session files to build the forced-capture list."""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
sites = json.loads((ROOT / "state/free_llm_chat_sites.json").read_text(encoding="utf-8"))
print("directory sites:", len(sites))
if isinstance(sites, dict):
    for name in sorted(sites):
        print(" ", name, "->", sites[name])
else:
    for s in sites:
        if isinstance(s, dict):
            print(" ", s.get("name", "?"), "->", s.get("url", "?"))
        else:
            print(" ", s)

print("\n--- existing session files ---")
secrets = sorted((ROOT / "state/secrets").glob("session_*.json"))
for s in secrets:
    print(" ", s.name)
