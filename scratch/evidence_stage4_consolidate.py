"""Stage 4: Consolidate all evidence + classify every provider into a GAP taxonomy.
Inputs: static + dynamic + noauth evidence, ledger.
Outputs:
  state/evidence/provider_evidence_consolidated.json  (full per-provider evidence)
  state/evidence/gap_analysis.json                    (gap taxonomy + actionable buckets)
"""
import json, os, datetime, collections

EV = "state/evidence"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

static = load(f"{EV}/provider_evidence_static.json")
dynamic = load(f"{EV}/provider_evidence_dynamic.json")
noauth = load(f"{EV}/provider_evidence_noauth.json")

prov = static["providers"]

# Index dynamic by provider
conn_tests_by_prov = collections.defaultdict(list)
for t in dynamic["connection_tests"]:
    conn_tests_by_prov[t["provider"]].append(t)
e2e_by_prov = collections.defaultdict(list)
for p in dynamic["e2e_probes"]:
    e2e_by_prov[p["provider"]].append(p)
noauth_by_prov = collections.defaultdict(list)
for p in noauth["probes"]:
    noauth_by_prov[p["provider"]].append(p)
log_errors = dynamic.get("log_errors", {})

# ---------- GAP taxonomy ----------
# Each provider -> one primary gap + evidence. Actionable buckets for follow-up.
GAP_DEFS = {
    "LIVE_VERIFIED": "E2E returned 200 with non-empty content proof",
    "LIVE_NO_CONTENT_PROOF": "E2E 200 but empty/None content (media or echo)",
    "NOAUTH_IP_RATELIMITED": "noAuth provider, upstream anti-abuse/rate-limit on this IP",
    "NOAUTH_UPSTREAM_MODEL_GONE": "noAuth provider, upstream rejects all model names (model drift/deprecation)",
    "NOAUTH_LOCAL_CLI_MISSING": "noAuth provider requires a local CLI binary not installed",
    "NOAUTH_UPSTREAM_DOWN": "noAuth provider, upstream fetch failed / endpoint gone",
    "NOAUTH_EGRESS_BLOCKED": "noAuth provider, upstream blocks this server egress (Vercel/geo)",
    "NOAUTH_MODEL_MAPPING_BUG": "noAuth provider, OmniRoute sends model=None (mapping bug)",
    "NOAUTH_WEB_SESSION_REQUIRED": "noAuth/web provider needs an interactive web session/thread",
    "OAUTH_REFRESH_EXPIRED": "OAuth connection present but refresh token expired (re-auth needed)",
    "OAUTH_ACTIVE": "OAuth connection valid and active",
    "APIKEY_MISSING": "Connection exists but API key missing/empty",
    "APIKEY_INVALID_401": "API key present but upstream 401 (invalid/expired key)",
    "APIKEY_CREDITS_EXHAUSTED": "API key valid but credits/quota exhausted (402/credits)",
    "APIKEY_FORBIDDEN_403": "API key present but upstream 403 (forbidden/geo/plan)",
    "APIKEY_MODEL_404": "Connection valid but probed model 404 (model name drift)",
    "APIKEY_TIMEOUT": "Upstream /v1/models or chat timed out",
    "WEB_COOKIE_REQUIRED": "web-cookie provider needs harvested browser cookie",
    "CLOUDFLARE_TLS_BLOCKED": "Authenticated but Cloudflare TLS-fingerprint block",
    "NO_SUBSCRIPTION": "Authenticated but no active paid subscription",
    "VALIDATION_UNSUPPORTED": "Provider has no validation endpoint (test not supported)",
    "NOT_CHAT_COMPLETABLE": "Non-LLM service (video/image/audio/search) - no chat path",
    "EXTERNAL_ACCOUNT_REQUIRED": "No connection configured; needs user account/API key",
    "NO_EXECUTOR": "No executor implementation in OmniRoute for this slug",
    "UNKNOWN": "Could not classify from available evidence",
}

def auth_class_from_registry(reg):
    """Derive the true auth mechanism from the registry file the provider was parsed from.
    The registry is organized by auth type, so the file path is the source of truth."""
    rf = (reg.get("registryFile") or "").lower()
    if not rf:
        return "unknown"
    if "noauth" in rf:
        return "noauth"
    if "web-cookie" in rf:
        return "web-cookie"
    if "oauth" in rf:
        return "oauth"
    if "apikey" in rf:
        return "apikey"
    if "local" in rf:
        return "local-cli"
    if "audio" in rf:
        return "audio"
    if "search" in rf:
        return "search"
    if "upstream-proxy" in rf:
        return "upstream-proxy"
    if "cloud-agent" in rf:
        return "cloud-agent"
    if "system" in rf:
        return "system"
    return "unknown"

def classify(slug, e):
    reg = e.get("registry") or {}
    noAuth = reg.get("noAuth")
    kinds = reg.get("serviceKinds") or []
    conns = e.get("connections") or []
    tests = conn_tests_by_prov.get(slug, [])
    e2es = e2e_by_prov.get(slug, [])
    nauth = noauth_by_prov.get(slug, [])
    has_executor = e.get("executor") is not None
    catalog = e.get("catalog_models") or []
    auth_class = auth_class_from_registry(reg)

    ev = []  # evidence strings
    ev.append(f"registryFile={reg.get('registryFile')} authClass={auth_class}")

    # Non-LLM service kinds -> not chat completable
    if kinds and not set(kinds) & {"llm"}:
        ev.append(f"serviceKinds={kinds} (no llm)")
        return "NOT_CHAT_COMPLETABLE", ev

    # E2E with content proof -> LIVE
    for p in e2es:
        if p.get("http_status") == 200 and p.get("has_content"):
            ev.append(f"E2E {p.get('model')} 200 content={p.get('content_preview','')[:40]!r}")
            return "LIVE_VERIFIED", ev
    for p in nauth:
        if p.get("http_status") == 200 and p.get("has_content"):
            ev.append(f"noAuth E2E {p.get('model')} 200 content={p.get('content_preview','')[:40]!r}")
            return "LIVE_VERIFIED", ev

    # E2E 200 but no content
    for p in e2es + nauth:
        if p.get("http_status") == 200 and not p.get("has_content"):
            ev.append(f"E2E {p.get('model')} 200 but empty content")
            return "LIVE_NO_CONTENT_PROOF", ev

    # noAuth providers: inspect probe errors
    if noAuth and nauth:
        for p in nauth:
            body = (p.get("body_preview") or "") + " " + (p.get("exception") or "")
            st = p.get("http_status")
            if "anti-abuse" in body or "ERR_BN_LIMIT" in body or "rate-limit" in body.lower() or st == 418:
                ev.append(f"{p.get('model')} -> {st} anti-abuse/rate-limit")
                return "NOAUTH_IP_RATELIMITED", ev
            if "Unsupported model" in body or "not known" in body or "Unknown" in body and "model" in body.lower():
                ev.append(f"{p.get('model')} -> {st} model rejected: {body[:80]}")
                # distinguish CLI-missing vs model-gone
                if "not recognized as an internal" in body or "CLI exited" in body:
                    return "NOAUTH_LOCAL_CLI_MISSING", ev
                if "Model None" in body:
                    return "NOAUTH_MODEL_MAPPING_BUG", ev
                return "NOAUTH_UPSTREAM_MODEL_GONE", ev
            if "not recognized as an internal" in body or "CLI exited" in body:
                ev.append(f"{p.get('model')} -> local CLI missing")
                return "NOAUTH_LOCAL_CLI_MISSING", ev
            if "fetch failed" in body or st == 502:
                ev.append(f"{p.get('model')} -> {st} fetch failed/upstream down")
                return "NOAUTH_UPSTREAM_DOWN", ev
            if "blocked by Vercel" in body or "egress" in body.lower() or st == 403:
                ev.append(f"{p.get('model')} -> {st} egress/geo block")
                return "NOAUTH_EGRESS_BLOCKED", ev
            if "thread creation" in body or "session" in body.lower():
                ev.append(f"{p.get('model')} -> web session/thread required")
                return "NOAUTH_WEB_SESSION_REQUIRED", ev
            if "Missing API key" in body or st == 401:
                ev.append(f"{p.get('model')} -> {st} needs API key despite noAuth flag")
                return "APIKEY_MISSING", ev
        ev.append("noAuth probe inconclusive")

    # Connections present: use test results
    if tests:
        # prefer an active valid test
        for t in tests:
            if t.get("valid") is True:
                ev.append(f"conn {t.get('connection_id','')[:8]} valid=True")
                # but E2E may have failed -> check e2e
                for p in e2es:
                    st = p.get("http_status")
                    body = p.get("body_preview", "")
                    if st == 404:
                        ev.append(f"E2E {p.get('model')} 404 model drift")
                        return "APIKEY_MODEL_404", ev
                    if st == 401:
                        ev.append(f"E2E {p.get('model')} 401 invalid key")
                        return "APIKEY_INVALID_401", ev
                    if st == 403:
                        ev.append(f"E2E {p.get('model')} 403 forbidden")
                        return "APIKEY_FORBIDDEN_403", ev
                    if st == 429:
                        ev.append(f"E2E {p.get('model')} 429 rate limited")
                        return "APIKEY_CREDITS_EXHAUSTED", ev
                return "OAUTH_ACTIVE" if (tests[0].get("authType") == "oauth") else "LIVE_VERIFIED", ev
        # invalid tests: classify by error
        for t in tests:
            err = (t.get("error") or "") + " " + (t.get("diagnosis_msg") or "")
            if "Refresh token expired" in err or "re-authenticate" in err:
                ev.append(f"conn {t.get('connection_id','')[:8]} refresh token expired")
                return "OAUTH_REFRESH_EXPIRED", ev
            if "Missing API key" in err:
                ev.append("conn missing API key")
                return "APIKEY_MISSING", ev
            if "No access token" in err:
                ev.append("conn no access token")
                return "OAUTH_REFRESH_EXPIRED", ev
            if "402" in err or "credits" in err.lower() or "subscription" in err.lower():
                ev.append(f"conn 402/credits: {err[:60]}")
                return "APIKEY_CREDITS_EXHAUSTED", ev
            if "no active paid subscription" in err.lower() or "subscription" in err.lower():
                ev.append("authenticated but no paid subscription")
                return "NO_SUBSCRIPTION", ev
            if "403" in err and ("anti-bot" in err.lower() or "cloudflare" in err.lower()):
                ev.append("Cloudflare TLS/anti-bot block")
                return "CLOUDFLARE_TLS_BLOCKED", ev
            if "timed out" in err.lower():
                ev.append(f"upstream timeout: {err[:60]}")
                return "APIKEY_TIMEOUT", ev
            if "validation endpoint not supported" in err.lower() or "test not supported" in err.lower():
                ev.append("no validation endpoint")
                return "VALIDATION_UNSUPPORTED", ev
            if "Cookie required" in err:
                ev.append("web-cookie required")
                return "WEB_COOKIE_REQUIRED", ev
            if "not installed" in err.lower() or "not recognized" in err.lower():
                ev.append("local CLI runtime not installed")
                return "NOAUTH_LOCAL_CLI_MISSING", ev
            if "fetch failed" in err.lower():
                ev.append("fetch failed")
                return "NOAUTH_UPSTREAM_DOWN", ev
        ev.append("connection test inconclusive")

    # No connections at all — classify by the registry's true auth mechanism
    if not conns and not tests:
        if auth_class == "apikey":
            ev.append("apikey provider, no connection configured")
            return "EXTERNAL_ACCOUNT_REQUIRED", ev
        if auth_class == "oauth":
            ev.append("oauth provider, no connection configured")
            return "EXTERNAL_ACCOUNT_REQUIRED", ev
        if auth_class == "web-cookie":
            ev.append("web-cookie provider, no session/cookie harvested")
            return "WEB_COOKIE_REQUIRED", ev
        if auth_class == "local-cli":
            ev.append("local-CLI provider, no connection configured")
            return "NOAUTH_LOCAL_CLI_MISSING", ev
        if auth_class in ("audio", "search", "upstream-proxy", "cloud-agent", "system"):
            ev.append(f"non-chat service class={auth_class}")
            return "NOT_CHAT_COMPLETABLE", ev
        if not has_executor:
            ev.append("no executor + no connection")
            return "NO_EXECUTOR", ev
        ev.append("no connection configured")
        return "EXTERNAL_ACCOUNT_REQUIRED", ev

    return "UNKNOWN", ev

# ---------- Run classification ----------
consolidated = {}
gap_buckets = collections.defaultdict(list)
for slug, e in prov.items():
    gap, ev = classify(slug, e)
    consolidated[slug] = {
        **e,
        "gap": gap,
        "gap_evidence": ev,
        "connection_tests": conn_tests_by_prov.get(slug, []),
        "e2e_probes": e2e_by_prov.get(slug, []),
        "noauth_probes": noauth_by_prov.get(slug, []),
        "log_errors": log_errors.get(slug, []),
    }
    gap_buckets[gap].append(slug)

# ---------- Actionable priority buckets ----------
ACTIONABLE = {
    "QUICK_WINS_reauth_oauth": sorted(gap_buckets.get("OAUTH_REFRESH_EXPIRED", [])),
    "QUICK_WINS_add_apikey": sorted(gap_buckets.get("APIKEY_MISSING", [])),
    "WEB_COOKIE_harvest": sorted(gap_buckets.get("WEB_COOKIE_REQUIRED", []) + gap_buckets.get("NOAUTH_WEB_SESSION_REQUIRED", [])),
    "MODEL_DRIFT_fix_names": sorted(gap_buckets.get("APIKEY_MODEL_404", []) + gap_buckets.get("NOAUTH_UPSTREAM_MODEL_GONE", []) + gap_buckets.get("NOAUTH_MODEL_MAPPING_BUG", [])),
    "CREDITS_top_up": sorted(gap_buckets.get("APIKEY_CREDITS_EXHAUSTED", [])),
    "IP_RATELIMIT_wait_or_proxy": sorted(gap_buckets.get("NOAUTH_IP_RATELIMITED", [])),
    "EGRESS_BLOCKED_proxy": sorted(gap_buckets.get("NOAUTH_EGRESS_BLOCKED", []) + gap_buckets.get("CLOUDFLARE_TLS_BLOCKED", [])),
    "LOCAL_CLI_install": sorted(gap_buckets.get("NOAUTH_LOCAL_CLI_MISSING", [])),
    "UPSTREAM_DOWN_monitor": sorted(gap_buckets.get("NOAUTH_UPSTREAM_DOWN", []) + gap_buckets.get("APIKEY_TIMEOUT", [])),
    "NEEDS_SUBSCRIPTION": sorted(gap_buckets.get("NO_SUBSCRIPTION", [])),
    "EXTERNAL_ACCOUNT_signup": sorted(gap_buckets.get("EXTERNAL_ACCOUNT_REQUIRED", [])),
    "NO_EXECUTOR_build": sorted(gap_buckets.get("NO_EXECUTOR", [])),
    "NOT_CHAT_COMPLETABLE": sorted(gap_buckets.get("NOT_CHAT_COMPLETABLE", [])),
    "ALREADY_LIVE": sorted(gap_buckets.get("LIVE_VERIFIED", []) + gap_buckets.get("LIVE_NO_CONTENT_PROOF", []) + gap_buckets.get("OAUTH_ACTIVE", [])),
}

os.makedirs(EV, exist_ok=True)
now = datetime.datetime.now().isoformat()

with open(f"{EV}/provider_evidence_consolidated.json", "w", encoding="utf-8") as f:
    json.dump({"generated_at": now, "providers": consolidated}, f, indent=1, ensure_ascii=False)

gap_summary = {g: {"count": len(s), "slugs": s} for g, s in sorted(gap_buckets.items())}
with open(f"{EV}/gap_analysis.json", "w", encoding="utf-8") as f:
    json.dump({
        "generated_at": now,
        "gap_definitions": GAP_DEFS,
        "gap_summary": gap_summary,
        "actionable_buckets": ACTIONABLE,
    }, f, indent=1, ensure_ascii=False)

print("=== GAP DISTRIBUTION ===")
for g, s in sorted(gap_buckets.items(), key=lambda x: -len(x[1])):
    print(f"  {len(s):4d}  {g}")
print(f"\nTOTAL classified: {sum(len(s) for s in gap_buckets.values())}")
print(f"\nWROTE consolidated + gap_analysis.json")
print("\n=== ACTIONABLE BUCKET SIZES ===")
for k, v in ACTIONABLE.items():
    print(f"  {len(v):4d}  {k}")
