#!/usr/bin/env python3
"""Real per-provider upstream scan for the unconfigured (EXTERNAL_ACCOUNT_REQUIRED) set.

Replaces the ASSUMED 'requires captcha/card/paywall' classification with a
MEASURED upstream verdict. For each provider that has a baseUrl in the app
catalog, we probe the upstream WITHOUT any credentials and record the observed
HTTP status + body snippet as evidence.

Probe strategy (cheapest first, no token consumption where possible):
  1. Derive a /models endpoint from the base URL when it looks OpenAI-compatible.
  2. GET /models unauthenticated -> classify reachability + auth enforcement.
  3. If /models is open (200), attempt a minimal unauthenticated chat completion
     to confirm the provider is genuinely usable without a key.

Verdict classes (observed, not assumed):
  OPEN_NO_AUTH        - 200 on models or chat with no credentials
  AUTH_REQUIRED       - 401/403 demanding a key/token
  PAYWALL_CREDITS     - 402 or credit/billing language
  CAPTCHA_BOT_BLOCK   - 403 with captcha/challenge/CF language, or hCaptcha
  RATE_LIMITED        - 429
  UPSTREAM_DOWN       - 5xx or connection failure
  NOT_FOUND           - 404 (endpoint shape wrong / retired)
  NEEDS_BROWSER       - web/graphql session endpoints that can't be probed via HTTP
  LOCAL_RUNTIME       - localhost endpoints (need local server, not external auth)
  UNKNOWN             - anything else (record raw status for manual review)

Output: state/provider_upstream_scan.json  (per-provider observed evidence)
Zero Terra tokens: pure local Python + requests.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASEURLS = ROOT / "state" / "provider_baseurls.json"
LEDGER = ROOT / "state" / "all_296_providers_execution_ledger.json"
OUT = ROOT / "state" / "provider_upstream_scan.json"

TIMEOUT = 12
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

CAPTCHA_RE = re.compile(
    r"captcha|hcaptcha|recaptcha|cf-chl|challenge|just a moment|verify you are human|"
    r"attention required|cloudflare|access denied|bot", re.I)
PAYWALL_RE = re.compile(
    r"credit|billing|payment|subscription|quota exceeded|insufficient|purchase|"
    r"upgrade|paid plan|balance", re.I)
AUTH_RE = re.compile(
    r"api[ _-]?key|unauthorized|invalid.*key|missing.*key|authentication required|"
    r"bearer|token required|forbidden|access token", re.I)


def classify(status: int, body: str, url: str) -> str:
    b = body[:4000]
    if status == 200:
        return "OPEN_NO_AUTH"
    if status == 402 or (status in (402, 403) and PAYWALL_RE.search(b)):
        return "PAYWALL_CREDITS"
    if status == 429:
        return "RATE_LIMITED"
    if status in (401, 403):
        if CAPTCHA_RE.search(b):
            return "CAPTCHA_BOT_BLOCK"
        if PAYWALL_RE.search(b):
            return "PAYWALL_CREDITS"
        if AUTH_RE.search(b) or status == 401:
            return "AUTH_REQUIRED"
        return "AUTH_REQUIRED"  # 403 default = blocked, treat as auth/wall
    if status == 404:
        return "NOT_FOUND"
    if 500 <= status < 600:
        return "UPSTREAM_DOWN"
    return "UNKNOWN"


def derive_models_url(base: str) -> str | None:
    """Derive a cheap /models probe URL from an OpenAI-compatible base URL."""
    b = base.rstrip("/")
    # strip known terminal path segments to reach the /v1 (or /openai/v1) root
    for suffix in ("/chat/completions", "/completions", "/messages", "/embeddings",
                   "/rerank", "/search", "/models"):
        if b.endswith(suffix):
            b = b[: -len(suffix)]
            break
    if re.search(r"/(v1|v2|v3|openai/v1|api/v1|api/v3)(/.*)?$", b) or b.endswith(("/v1", "/v2", "/v3")):
        return b.rstrip("/") + "/models"
    return None


def is_local(base: str) -> bool:
    return bool(re.match(r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)", base))


def is_browser_session(base: str, auth_type: str | None) -> bool:
    """Web/graphql/admin endpoints that can't be meaningfully probed via plain HTTP."""
    if auth_type in ("cookie", "oauth"):
        return True
    web_markers = ("/app", "graphql", "admin-ajax", "backend-api/conversation",
                   "rest/app-chat", "/api/chat", "designerapp", "wp-admin",
                   "generate-proxy", "rest/sse")
    return any(m in base for m in web_markers)


def probe_one(slug: str, meta: dict) -> dict:
    base = meta["baseUrl"]
    auth_type = meta.get("authType")
    result = {
        "slug": slug,
        "baseUrl": base,
        "declared_authType": auth_type,
    }

    if is_local(base):
        # local runtime: check if the port answers at all
        try:
            r = requests.get(base, timeout=5, headers=HEADERS)
            result.update(verdict="LOCAL_RUNTIME", status=r.status_code,
                          note="localhost endpoint responds; needs local server configured")
        except Exception as e:
            result.update(verdict="LOCAL_RUNTIME", status=None,
                          note=f"localhost endpoint not responding: {type(e).__name__}")
        return result

    if is_browser_session(base, auth_type):
        result.update(verdict="NEEDS_BROWSER", status=None,
                      note="web/session/graphql endpoint; requires browser session, not plain HTTP probe")
        return result

    # 1) cheap /models probe
    models_url = derive_models_url(base)
    probe_url = models_url or base
    try:
        r = requests.get(probe_url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
        body = r.text
        verdict = classify(r.status_code, body, probe_url)
        result.update(verdict=verdict, status=r.status_code,
                      probed=probe_url, body_snippet=body[:300])
    except requests.exceptions.SSLError as e:
        result.update(verdict="UPSTREAM_DOWN", status=None, probed=probe_url,
                      note=f"SSL error: {str(e)[:120]}")
        return result
    except Exception as e:
        result.update(verdict="UPSTREAM_DOWN", status=None, probed=probe_url,
                      note=f"{type(e).__name__}: {str(e)[:120]}")
        return result

    # 2) if models open, confirm with a minimal unauthenticated chat completion
    if result.get("verdict") == "OPEN_NO_AUTH" and models_url:
        chat_url = re.sub(r"/models$", "/chat/completions", models_url)
        payload = {"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
        try:
            r2 = requests.post(chat_url, json=payload, timeout=TIMEOUT, headers=HEADERS)
            chat_verdict = classify(r2.status_code, r2.text, chat_url)
            result["chat_probe"] = {"url": chat_url, "status": r2.status_code,
                                    "verdict": chat_verdict, "snippet": r2.text[:200]}
            # if chat is blocked but models open, downgrade
            if chat_verdict != "OPEN_NO_AUTH":
                result["verdict"] = chat_verdict
                result["note"] = "models open but chat completion requires auth/credits"
        except Exception as e:
            result["chat_probe"] = {"url": chat_url, "error": f"{type(e).__name__}"}

    return result


def main() -> int:
    baseurls = json.loads(BASEURLS.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["providers"]
    ext = {k: v for k, v in ledger.items()
           if (v.get("status") if isinstance(v, dict) else v) == "EXTERNAL_ACCOUNT_REQUIRED"}
    targets = {k: baseurls[k] for k in ext if k in baseurls}
    print(f"scanning {len(targets)} unconfigured providers with upstream baseUrls\n")

    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(probe_one, slug, meta): slug for slug, meta in targets.items()}
        done = 0
        for fut in as_completed(futs):
            slug = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"slug": slug, "verdict": "UNKNOWN", "note": f"probe crashed: {e}"}
            results[slug] = res
            done += 1
            print(f"  [{done:3d}/{len(targets)}] {slug:24s} {res.get('verdict'):18s} "
                  f"status={res.get('status')}")

    # tally
    from collections import Counter
    tally = Counter(r.get("verdict") for r in results.values())
    print("\n=== VERDICT TALLY (observed, not assumed) ===")
    for verdict, n in tally.most_common():
        print(f"  {verdict:20s} {n}")

    OUT.write_text(json.dumps({"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "count": len(results), "tally": dict(tally),
                               "results": results}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
