"""Verify the 14 NEEDS_BROWSER targets' ledger entries are recorded honestly.

chatgpt-web + grok-web + zed-hosted already finalized. This checks the other 11.
"""
import json

LEDGER = r"d:\omniroute-monetizer\state\all_296_providers_execution_ledger.json"

# The 14 original NEEDS_BROWSER targets and their expected final states
TARGETS = {
    "chatgpt-web": "LIVE_ACTIVE",
    "grok-web": "BLOCKED_CLOUDFLARE_ANTIBOT",
    "zed-hosted": "BLOCKED_OAUTH_FLOW",
    "udio": "BLOCKED_CAPTCHA",
    "suno": "BLOCKED_CAPTCHA",
    "microsoft-designer-web": "BLOCKED_AUTH_REQUIRED",  # OAUTH_ONLY
    "adapta-web": "BLOCKED_BROWSER_SESSION",  # EMAIL_SIGNUP_POSSIBLE
    "veoaifree-web": "BLOCKED_BROWSER_SESSION",  # EMAIL_SIGNUP_POSSIBLE
    "muse-spark-web": "BLOCKED_UNVERIFIED",  # 403 bot-blocked
    "blackbox": "BLOCKED_BROWSER_SESSION",  # JS-heavy SPA deferred
    "perplexity-web": "BLOCKED_BROWSER_SESSION",  # JS-heavy SPA deferred
    "t3-web": "BLOCKED_BROWSER_SESSION",  # JS-heavy SPA deferred
    "yuanbao-web": "BLOCKED_BROWSER_SESSION",  # JS-heavy SPA deferred
    "codebuddy-cn": "BLOCKED_BROWSER_SESSION",  # JS-heavy SPA deferred
}

with open(LEDGER, encoding="utf-8") as f:
    data = json.load(f)

providers = data["providers"]
print(f"Ledger: {len(providers)} providers\n")

missing = []
mismatch = []
ok = []
for slug, expected in TARGETS.items():
    entry = providers.get(slug)
    if entry is None:
        missing.append(slug)
        print(f"[MISSING] {slug} — not in ledger")
        continue
    status = entry.get("status")
    verdict = entry.get("observed_verdict", "")
    details = entry.get("details", {})
    blocker = details.get("blocker", "")[:100] if isinstance(details, dict) else ""
    marker = "OK" if status == expected else "CHECK"
    if status != expected:
        mismatch.append((slug, expected, status))
    else:
        ok.append(slug)
    print(f"[{marker}] {slug}: status={status} verdict={verdict}")
    if blocker:
        print(f"        blocker: {blocker}")

print(f"\nSummary: {len(ok)} match expected, {len(mismatch)} differ, {len(missing)} missing")
for slug, exp, got in mismatch:
    print(f"  DIFFERS: {slug} expected={exp} actual={got}")
