"""Update ledger for wave-1 providers with honest classifications (backup-first)."""
import json
import os
import shutil
from datetime import datetime, timezone

PATH = "state/all_296_providers_execution_ledger.json"
BACKUP = PATH + ".bak-123-" + datetime.now().strftime("%Y%m%d-%H%M%S")

shutil.copy2(PATH, BACKUP)
print(f"backup -> {BACKUP}")

with open(PATH, "r", encoding="utf-8") as f:
    d = json.load(f)
provs = d.get("providers", d)

NOW = datetime.now(timezone.utc).isoformat()

updates = {
    "perplexity-web": {
        "status": "AUTHENTICATED_FREE_PLAN_NO_COMPLETION",
        "in_db_connections": 1,
        "category": "Third-Party Cloud Provider (Browser Session — Free Plan)",
        "details": {
            "connection_id": "3b45f2bf-f1aa-4162-a305-ace36bddd4b7",
            "blocker": "Real Google SSO login completed (strong cookie __Secure-next-auth.session-token len=517; browser query answered correctly). But OmniRoute executor returns HTTP 200 with empty content (out=0 tokens) for all models — account is Free plan; executor requires Pro/Max subscription session (upstream PRs #6955/#7930).",
            "safe_handling": "Injected + test valid=True but NOT LIVE (no completion text). Needs Pro/Max account for real completions.",
        },
        "observed_verdict": "AUTHENTICATED_NO_COMPLETION",
        "evidence": "worklog #123: visual login verified; browser query '2+2' answered '4'; /v1/chat/completions HTTP 200 but out=0 tokens for pplx-sonar/auto/glm/kimi/nemotron/gpt-5.6-terra; app.log ProxyEgress status=success + USAGE in=592 out=0",
        "last_updated": NOW,
    },
    "blackbox-web": {
        "status": "AUTHENTICATED_NO_SUBSCRIPTION",
        "in_db_connections": 1,
        "category": "Third-Party Cloud Provider (Browser Session — No Paid Subscription)",
        "details": {
            "connection_id": "bc73b1a8-f125-4931-bc96-e45b74ebe91c",
            "blocker": "Real Google SSO login completed (next-auth.session-token present; app.blackbox.ai shows signed-in 'Kunal Das'). test_connection valid=False: 'no active paid subscription was detected for premium web models'. E2E returns 'Deprecated endpoint'.",
            "safe_handling": "Injected but NOT LIVE. Needs paid Blackbox subscription.",
        },
        "observed_verdict": "AUTHENTICATED_NO_SUBSCRIPTION",
        "evidence": "worklog #123: visual login verified; test_connection HTTP 200 valid=False (no paid subscription); E2E 'Deprecated endpoint'",
        "last_updated": NOW,
    },
    "t3-web": {
        "status": "AUTHENTICATED_RATE_LIMITED",
        "in_db_connections": 1,
        "category": "Third-Party Cloud Provider (Browser Session — Rate Limited)",
        "details": {
            "connection_id": "ef5082c2-e57e-4a6d-8e99-0e0cad698fbd",
            "blocker": "Real Google SSO login completed (strong cookies session/access-token/wos-session). Prefixed models t3-web/<model> route correctly to POST https://t3.chat/api/chat but upstream returns 429 't3.chat rate limited' on all models across retries — free account quota exhausted.",
            "safe_handling": "Injected + auth working (429 not 401). NOT LIVE this session; may recover after quota reset.",
        },
        "observed_verdict": "AUTHENTICATED_RATE_LIMITED",
        "evidence": "worklog #123: app.log shows real upstream POST t3.chat/api/chat reached; [429] t3.chat rate limited (reset after 3s) x3 retries x3 models",
        "last_updated": NOW,
    },
    "muse-spark-web": {
        "status": "BLOCKED_NO_GOOGLE_SSO",
        "in_db_connections": 0,
        "category": "Third-Party Cloud Provider (No Account Configured)",
        "details": {
            "blocker": "meta.ai auth (auth.meta.com) offers ONLY Facebook / Instagram / email+mobile — NO Google SSO option. Our Google account cannot be used; no Meta credentials available.",
            "safe_handling": "Suppressed from cascades. Needs Facebook/Instagram credentials to proceed.",
        },
        "observed_verdict": "BLOCKED_NO_GOOGLE_SSO_NEEDS_META_CREDS",
        "evidence": "worklog #123: clicked meta.ai 'Log in' -> auth.meta.com shows only 'Continue with Facebook' / 'Continue with Instagram' / 'Use mobile number or email'",
        "last_updated": NOW,
    },
}

for slug, upd in updates.items():
    if slug in provs:
        provs[slug].update(upd)
        print(f"updated {slug} -> {upd['status']}")
    else:
        print(f"!! {slug} not found in ledger")

with open(PATH, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("ledger saved")
