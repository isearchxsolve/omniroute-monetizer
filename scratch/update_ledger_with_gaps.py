import json
from datetime import datetime

# Load consolidated evidence
with open("state/evidence/provider_evidence_consolidated.json", encoding="utf-8") as f:
    consolidated = json.load(f)

# Load ledger
with open("state/all_296_providers_execution_ledger.json", encoding="utf-8") as f:
    ledger = json.load(f)

providers = ledger["providers"]

# Update each provider's status based on our gap analysis
updated_count = 0
for slug, provider in providers.items():
    if slug in consolidated["providers"]:
        gap = consolidated["providers"][slug]["gap"]
        # Map our gap taxonomy to ledger status values
        status_mapping = {
            "LIVE_VERIFIED": "LIVE_ACTIVE",
            "LIVE_NO_CONTENT_PROOF": "LIVE_ACTIVE", 
            "OAUTH_ACTIVE": "LIVE_ACTIVE",
            "EXTERNAL_ACCOUNT_REQUIRED": "EXTERNAL_ACCOUNT_REQUIRED",
            "WEB_COOKIE_REQUIRED": "BLOCKED_WEB_SESSION",
            "NOAUTH_LOCAL_CLI_MISSING": "BLOCKED_LOCAL_RUNTIME",
            "NOT_CHAT_COMPLETABLE": "NOT_CHAT_COMPLETABLE",
            "NOAUTH_IP_RATELIMITED": "BLOCKED_RATE_LIMITED",
            "NOAUTH_UPSTREAM_MODEL_GONE": "BLOCKED_UPSTREAM_DOWN",
            "NOAUTH_MODEL_MAPPING_BUG": "BLOCKED_VALIDATION_UNSUPPORTED",
            "NOAUTH_WEB_SESSION_REQUIRED": "BLOCKED_WEB_SESSION",
            "OAUTH_REFRESH_EXPIRED": "BLOCKED_AUTH_REQUIRED",
            "APIKEY_MISSING": "BLOCKED_AUTH_REQUIRED",
            "APIKEY_INVALID_401": "BLOCKED_AUTH_REQUIRED",
            "APIKEY_CREDITS_EXHAUSTED": "BLOCKED_CREDITS",
            "APIKEY_FORBIDDEN_403": "BLOCKED_FORBIDDEN",
            "APIKEY_TIMEOUT": "BLOCKED_UPSTREAM_DOWN",
            "APIKEY_MODEL_404": "BLOCKED_VALIDATION_UNSUPPORTED",
            "VALIDATION_UNSUPPORTED": "BLOCKED_VALIDATION_UNSUPPORTED",
            "CLOUDFLARE_TLS_BLOCKED": "AUTHENTICATED_CLOUDFLARE_TLS_BLOCKED",
            "NO_SUBSCRIPTION": "AUTHENTICATED_FREE_PLAN_NO_COMPLETION",
            "NO_EXECUTOR": "BLOCKED_ENDPOINT_GONE",
            "UNKNOWN": "BLOCKED_UNVERIFIED"
        }
        
        new_status = status_mapping.get(gap, "BLOCKED_UNVERIFIED")
        if provider.get("status") != new_status:
            provider["status"] = new_status
            updated_count += 1
            # Also update details if we have gap evidence
            evidence = consolidated["providers"][slug].get("gap_evidence", [])
            if evidence:
                provider["details"] = {
                    "blocker": "; ".join(evidence[:2]),  # Keep first two pieces of evidence
                    "safe_handling": "Based on automated evidence collection"
                }

# Update timestamp
ledger["timestamp"] = datetime.now().isoformat()

# Write back ledger
with open("state/all_296_providers_execution_ledger.json", "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=2, ensure_ascii=False)

print(f"Updated {updated_count} providers in ledger")
print(f"Ledger timestamp updated to: {ledger['timestamp']}")

# Quick verification
status_counts = {}
for provider in providers.values():
    status = provider.get("status", "UNKNOWN")
    status_counts[status] = status_counts.get(status, 0) + 1

print("\\nStatus distribution after update:")
for status, count in sorted(status_counts.items()):
    print(f"  {count:3d} {status}")