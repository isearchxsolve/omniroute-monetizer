"""Fix over-matched ledger entries; keep gemini-web LIVE_ACTIVE; correct status_counts."""
import json
from datetime import datetime, timezone

PATH = "state/all_296_providers_execution_ledger.json"
d = json.load(open(PATH, encoding="utf-8"))
provs = d["providers"]

now = datetime.now(timezone.utc).isoformat()

# 1. g4f-gemini: restore to BLOCKED_CREDITS (siblings g4f-groq/g4f-nvidia/g4f-pollinations pattern)
e = provs["g4f-gemini"]
e["status"] = "BLOCKED_CREDITS"
for k in ("verdict", "evidence", "updated_at"):
    e.pop(k, None)

# 2. gemini-business: restore to EXTERNAL_ACCOUNT_REQUIRED (no observed_verdict, unscanned)
e = provs["gemini-business"]
e["status"] = "EXTERNAL_ACCOUNT_REQUIRED"
for k in ("verdict", "evidence", "updated_at"):
    e.pop(k, None)

# 3. gemini (AI Studio key): was already LIVE_ACTIVE; remove wrongly-added fields
e = provs["gemini"]
e["status"] = "LIVE_ACTIVE"
for k in ("verdict", "evidence", "updated_at"):
    e.pop(k, None)

# 4. gemini-web: correct target — keep LIVE_ACTIVE, refresh details to reflect reality
e = provs["gemini-web"]
e["status"] = "LIVE_ACTIVE"
e["verdict"] = "LIVE"
e["in_db_connections"] = 1
e["connection_id"] = "c24d66d8-d494-4aee-902c-6e672a232a71"
e["details"] = {
    "resolution": "Browser-session harvest 2026-08-18: cookies from existing logged-in Chrome profile "
                  "injected via OmniRoute API; OmniRoute test valid=true; 3 models synced.",
    "runtime_fix": "browsers.json restored to playwright-core dist + PLAYWRIGHT_BROWSERS_PATH override "
                   "in C:\\Users\\Admin\\.omniroute\\.env (LocalSystem service has no LOCALAPPDATA) + full NSSM restart.",
    "e2e": "2026-08-18: /v1/chat/completions HTTP 200 on all 3 models "
           "(gemini-3.5-flash 20.1s, gemini-3.1-flash-lite 12.4s, gemini-3.1-pro 12.1s), "
           "content 'LIVE', x-omniroute-provider=gweb, cache-hit=false.",
}
e["updated_at"] = now

# 5. status_counts: gemini-web BLOCKED_BROWSER_SESSION -> LIVE_ACTIVE (net +1 LIVE, -1 BROWSER_SESSION)
sc = d.get("status_counts")
if isinstance(sc, dict):
    sc["LIVE_ACTIVE"] = sc.get("LIVE_ACTIVE", 20) + 1
    sc["BLOCKED_BROWSER_SESSION"] = max(sc.get("BLOCKED_BROWSER_SESSION", 15) - 1, 0)

json.dump(d, open(PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("saved.")
print("g4f-gemini:", provs["g4f-gemini"]["status"])
print("gemini-business:", provs["gemini-business"]["status"])
print("gemini:", provs["gemini"]["status"], "| has evidence key:", "evidence" in provs["gemini"])
print("gemini-web:", provs["gemini-web"]["status"], provs["gemini-web"]["verdict"])
print("status_counts LIVE_ACTIVE:", sc.get("LIVE_ACTIVE"), "BLOCKED_BROWSER_SESSION:", sc.get("BLOCKED_BROWSER_SESSION"))
