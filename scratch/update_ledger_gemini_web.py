"""Update ledger: gemini-web -> LIVE_ACTIVE with measured e2e evidence."""
import json
from datetime import datetime, timezone

PATH = "state/all_296_providers_execution_ledger.json"
d = json.load(open(PATH, encoding="utf-8"))

EVIDENCE = (
    "E2E VERIFIED 2026-08-18: real /v1/chat/completions HTTP 200 via harvested browser session. "
    "gemini-3.5-flash 20.1s, gemini-3.1-flash-lite 12.4s, gemini-3.1-pro 12.1s; "
    "all returned content 'LIVE', x-omniroute-provider=gweb, cache-hit=false. "
    "Fix chain: browsers.json copy + PLAYWRIGHT_BROWSERS_PATH in .env + full NSSM restart."
)

def update(entry):
    entry["status"] = "LIVE_ACTIVE"
    entry["verdict"] = "LIVE"
    entry["evidence"] = EVIDENCE
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()

found = 0
if isinstance(d, dict):
    containers = [d]
    for v in d.values():
        if isinstance(v, (list, dict)):
            containers.append(v)
    for c in containers:
        if isinstance(c, list):
            for e in c:
                if isinstance(e, dict) and "gemini-web" in json.dumps(e.get("provider", "")) + json.dumps(e.get("id", "")) + json.dumps(e.get("name", "")):
                    update(e); found += 1
        elif isinstance(c, dict):
            for k, e in c.items():
                if "gemini" in k.lower() and isinstance(e, dict):
                    update(e); found += 1
elif isinstance(d, list):
    for e in d:
        if isinstance(e, dict) and "gemini" in json.dumps(e).lower() and "web" in json.dumps(e).lower():
            update(e); found += 1

print("updated entries:", found)
if found:
    json.dump(d, open(PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("saved", PATH)
else:
    print("NOT SAVED - no gemini-web entry found; dumping structure for inspection")
    if isinstance(d, dict):
        print("top keys:", list(d.keys()))
        for k, v in d.items():
            if isinstance(v, list) and v:
                print(f"  {k}: list[{len(v)}] sample keys:", list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]))
