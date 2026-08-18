"""Apply the real signup-flow classifications (worklog #116) to 5 ledger entries
that still carry generic pre-classification statuses.

Source of truth: state/signup_flow_classification_14.json + _pass2.json, worklog #116.
Backup-first, JSON-validated, status_counts recomputed.
"""
import json
import shutil
import datetime
import sys

LEDGER = r"d:\omniroute-monetizer\state\all_296_providers_execution_ledger.json"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = LEDGER.replace(".json", f"_backup_{ts}.json")
shutil.copy2(LEDGER, backup)
print(f"Backup: {backup}")

with open(LEDGER, encoding="utf-8") as f:
    data = json.load(f)

providers = data["providers"]

CLASSIFY_EVIDENCE = (
    "signup-flow classification 2026-08-18 "
    "(state/signup_flow_classification_14.json + _pass2.json; worklog #116)"
)

updates = {
    "udio": {
        "status": "BLOCKED_CAPTCHA",
        "observed_verdict": "DISCARD_CAPTCHA",
        "blocker": (
            "Signup flow reaches hCaptcha (invisible mode escalating to image "
            "challenge). Per user captcha policy (2026-08-16): never solve "
            "captchas, discard immediately."
        ),
        "evidence_append": (
            f" | {CLASSIFY_EVIDENCE}: verdict DISCARD_CAPTCHA (hCaptcha on signup)"
        ),
    },
    "suno": {
        "status": "BLOCKED_CAPTCHA",
        "observed_verdict": "DISCARD_CAPTCHA",
        "blocker": (
            "Signup flow protected by hCaptcha + Cloudflare Turnstile. Per user "
            "captcha policy (2026-08-16): never solve captchas, discard immediately."
        ),
        "evidence_append": (
            f" | {CLASSIFY_EVIDENCE}: verdict DISCARD_CAPTCHA (hcaptcha + turnstile markers)"
        ),
    },
    "microsoft-designer-web": {
        "status": "BLOCKED_AUTH_REQUIRED",
        "observed_verdict": "OAUTH_ONLY",
        "blocker": (
            "Microsoft SSO OAuth only (designer.microsoft.com): no email/password "
            "signup path exists; requires the user's interactive Microsoft account "
            "login. Not automatable without user-provided session."
        ),
        "evidence_append": (
            f" | {CLASSIFY_EVIDENCE}: verdict OAUTH_ONLY (microsoft_sso marker)"
        ),
    },
    "muse-spark-web": {
        "status": "BLOCKED_UNVERIFIED",
        "observed_verdict": "BOT_BLOCKED_403",
        "blocker": (
            "www.meta.ai returns HTTP 403 to plain HTTP probes (bot-blocked); SPA "
            "serves empty HTML without JS rendering; /api/graphql returns 405. "
            "Cannot verify without a browser-rendered pass; deferred."
        ),
        "evidence_append": (
            f" | {CLASSIFY_EVIDENCE}: HTTP 403 on www.meta.ai, "
            "SPA_EMPTY_HTML_NEEDS_BROWSER"
        ),
    },
    "blackbox": {
        "status": "BLOCKED_BROWSER_SESSION",
        "observed_verdict": "JS_HEAVY_SPA_DEFERRED",
        "blocker": (
            "www.blackbox.ai is a JS-heavy SPA: /login returns 200 but no auth "
            "markers are visible to plain fetch; /api/auth/session 404. No public "
            "OpenAI-compatible API (api.blackbox.ai/v1/models 404 = web-only "
            "provider, not a gone endpoint). Needs a browser-rendered pass; deferred."
        ),
        "evidence_append": (
            f" | {CLASSIFY_EVIDENCE}: JS-heavy SPA (login 200, no auth markers); "
            "reclassified from BLOCKED_ENDPOINT_GONE (the 404 was the API probe, "
            "the web app itself is up)"
        ),
    },
}

changed = []
for slug, upd in updates.items():
    entry = providers.get(slug)
    if entry is None:
        print(f"[SKIP] {slug} not in ledger")
        continue
    old_status = entry.get("status")
    entry["status"] = upd["status"]
    entry["observed_verdict"] = upd["observed_verdict"]
    entry.setdefault("details", {})["blocker"] = upd["blocker"]
    entry["evidence"] = entry.get("evidence", "") + upd["evidence_append"]
    changed.append((slug, old_status, upd["status"]))
    print(f"[UPDATED] {slug}: {old_status} -> {upd['status']} ({upd['observed_verdict']})")

# Recompute status_counts
counts = {}
for p in providers.values():
    s = p.get("status", "UNKNOWN")
    counts[s] = counts.get(s, 0) + 1
data["status_counts"] = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
data["last_updated"] = datetime.datetime.now().isoformat(timespec="seconds")

with open(LEDGER, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=1, ensure_ascii=False)

# Re-validate
with open(LEDGER, encoding="utf-8") as f:
    check = json.load(f)
assert len(check["providers"]) == 296, f"provider count changed: {len(check['providers'])}"
print(f"\nJSON OK, providers: {len(check['providers'])}")
print(f"Changed: {len(changed)}")
print("\nNew status_counts:")
for k, v in check["status_counts"].items():
    print(f"  {k}: {v}")
