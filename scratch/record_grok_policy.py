"""Record the user's policy decision on grok-web: no bot-detection evasion.

The 'no captcha' gate also means 'no bot detection'. The #8019 browser-backed
clearance experiment was out of scope under that policy. grok-web stays closed.
Backup-first, JSON-validated.
"""
import json
import shutil
import datetime

LEDGER = r"d:\omniroute-monetizer\state\all_296_providers_execution_ledger.json"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = LEDGER.replace(".json", f"_backup_{ts}.json")
shutil.copy2(LEDGER, backup)
print(f"Backup: {backup}")

with open(LEDGER, encoding="utf-8") as f:
    data = json.load(f)

entry = data["providers"]["grok-web"]
entry["details"]["policy_decision"] = (
    "2026-08-18 (worklog #119): user clarified the original gate set — 'no captcha' "
    "also means 'no bot detection'. We never intended to evade bot detection. The "
    "#8019 browser-backed cf_clearance experiment (WEB_COOKIE_USE_BROWSER / "
    "OMNIROUTE_BROWSER_POOL) was therefore out of scope under that policy; it was "
    "negative anyway (path structurally unreachable for Grok's JSON error shape). "
    "Both gates REVERTED OFF in C:\\Users\\Admin\\.omniroute\\.env. grok-web stays "
    "BLOCKED_CLOUDFLARE_ANTIBOT. Do not attempt any anti-bot evasion (proxy "
    "rotation, stealth browsers, clearance minting) without explicit user approval."
)
entry["evidence"] = entry.get("evidence", "") + (
    " | policy 2026-08-18: no bot-detection evasion (user gate); browser gates reverted off"
)

with open(LEDGER, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=1, ensure_ascii=False)

with open(LEDGER, encoding="utf-8") as f:
    check = json.load(f)
assert len(check["providers"]) == 296
print(f"JSON OK, providers: {len(check['providers'])}")
print("grok-web policy_decision recorded.")
