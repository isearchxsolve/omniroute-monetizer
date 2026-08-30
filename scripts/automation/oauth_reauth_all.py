#!/usr/bin/env python3
"""
OAuth Re-Authentication Script — OmniRoute Monetizer
Re-authenticates all expired OAuth providers using the OmniRoute dashboard's
OAuth flow, Playwright browser automation with the persistent browser profile,
and the direct /api/oauth/{provider}/exchange endpoint where applicable.

SECURITY: Never logs tokens, api keys, passwords, or any credentials.
          Redacts all sensitive fields before printing.

Flow per provider type:
  1. Google OAuth (antigravity/agy): GET /api/oauth/{p}/authorize -> browser popup -> exchange
  2. PKCE callback server (xai-oauth/grok-cli/codex): GET /api/oauth/{p}/start-callback-server -> browser popup -> poll
  3. Device code (kimi-coding/amazon-q/kilocode): GET /api/oauth/{p}/device-code -> user enters code
  4. windsurf: import-token via /api/oauth/windsurf/import-token (requires token from IDE)
  5. trae: import via DevTools JWT capture (requires manual step)
  6. cline: browser OAuth via /api/oauth/cline/authorize
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# ─── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8")

from password_vault import retrieve_password  # noqa: E402
import requests  # noqa: E402

OMNI_BASE = "http://127.0.0.1:20128"
BROWSER_PROFILE = str(PROJECT_ROOT / "state" / "browser_profile")
RESULTS_FILE = PROJECT_ROOT / "state" / "oauth_reauth_results.json"

# Single Chrome instance already running with ALL accounts logged in
# C:\Users\Admin\AppData\Local\Google\Chrome\User Data on CDP port 9222
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA = r"C:\Users\Admin\AppData\Local\Google\Chrome\User Data"
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

# ─── Redaction ───────────────────────────────────────────────────────────────
SECRET_PATTERNS = re.compile(
    r"(token|key|secret|password|code|verifier|credential|bearer|authorization)",
    re.I,
)

def log(msg: str) -> None:
    # Never log secret-looking lines
    if SECRET_PATTERNS.search(msg) and any(c in msg for c in ["=", ":", "Bearer", "sk-", "eyJ"]):
        print(f"[{time.strftime('%H:%M:%S')}] [REDACTED - secret detected in log line]")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ─── Provider definitions ─────────────────────────────────────────────────────
# (connection_id, provider_name, email/name, auth_method, google_email_for_account_picker)
PROVIDERS_TO_REAUTH = [
    # Google OAuth providers (antigravity / agy) — use authorize + exchange
    ("4bb06b19-4481-4855-9e96-8899fddf543e", "antigravity", "xxpertcomments@gmail.com",   "google_oauth", "xxpertcomments@gmail.com"),
    ("4b688ac0-67a6-4fea-9da2-73547aab7b94", "antigravity", "kunal.colab@gmail.com",      "google_oauth", "kunal.colab@gmail.com"),
    ("b727fc55-1a8c-44aa-942d-d48336ba611a", "antigravity", "isearch.xsolve@gmail.com",   "google_oauth", "isearch.xsolve@gmail.com"),
    ("7bbcc7ab-1c75-4e30-a20b-a63d4e6cf156", "antigravity", "niloydassana@gmail.com",     "google_oauth", "niloydassana@gmail.com"),
    ("a4809bf3-13c4-4e74-ae85-114ef6c83f66", "agy",         "isearch.xsolve@gmail.com",   "google_oauth", "isearch.xsolve@gmail.com"),
    # cline — browser OAuth (cline.bot)
    ("c8a7f56f-1753-483a-b593-5fdcf83b1dc2", "cline",       "Kunal Das",                  "browser_oauth", None),
    # codex (OpenAI) — PKCE callback server on port 1455
    ("db2f61d1-a5cb-422b-8275-f2a21e82f0f7", "codex",       "xxpertcomments@gmail.com",   "pkce_callback", None),
    # xai-oauth — PKCE callback server on port 56121
    ("b34d58dc-7870-44cb-ac64-f623c7a88505", "xai-oauth",   "xxpertcomments@gmail.com",   "pkce_callback", None),
    # grok-cli — PKCE callback server on port 56122
    ("414a9dff-c750-4e3b-890f-f93c4c906c76", "grok-cli",    "kunal_nit@yahoo.co.in",      "pkce_callback", None),
    # Device code flows
    ("f1a76219-781c-4f2f-85b1-1261af52ec32", "kimi-coding",  None,                         "device_code",   None),
    ("f76e4db5-55ed-4fe6-93c3-418445ae862a", "amazon-q",     None,                         "device_code",   None),
    ("2248a0bf-72b8-41c8-b079-2d21cd41bb64", "amazon-q",     None,                         "device_code",   None),
    ("6f3af471-59c9-4370-9214-fcee7f8aaaa8", "kilocode",     "xxpertcomments@gmail.com",   "device_code",   None),
    # windsurf — import-token (needs IDE to generate)
    ("39458046-d0bf-4633-a96d-3addcfc5513d", "windsurf",     None,                         "import_token",  None),
    ("179e4825-1e03-47de-accc-c6cb611a195c", "windsurf",     None,                         "import_token",  None),
    # trae — import via DevTools JWT (manual step)
    ("ad3b1ec6-3f17-4b7b-8388-0002e5c3d8b7", "trae",        "kunal.colab@gmail.com",       "import_token",  None),
]

# ─── OmniRoute API session ───────────────────────────────────────────────────
def get_api_session() -> requests.Session:
    pw = retrieve_password(PROJECT_ROOT / "state" / "omniroute_password.bin")
    session = requests.Session()
    session.trust_env = False  # bypass loopback proxy that intercepts 127.0.0.1
    r = session.post(f"{OMNI_BASE}/api/auth/login", json={"password": pw})
    assert r.status_code == 200, f"Login failed: {r.status_code}"
    return session

# ─── Device code flow ────────────────────────────────────────────────────────
def handle_device_code(session: requests.Session, conn_id: str, provider: str) -> dict:
    """Start device code flow, return instructions + poll result."""
    r = session.get(f"{OMNI_BASE}/api/oauth/{provider}/device-code", timeout=30)
    if not r.ok:
        return {"success": False, "error": f"device-code start failed: {r.status_code} {r.text[:100]}"}
    
    data = r.json()
    user_code = data.get("user_code", "N/A")
    verification_uri = data.get("verification_uri", "N/A")
    expires_in = data.get("expires_in", 900)
    
    log(f"[{provider}] DEVICE CODE: {user_code}")
    log(f"[{provider}] Visit: {verification_uri}")
    # Surface codes for the operator (non-redacted) so they can complete the flow
    try:
        with open(PROJECT_ROOT / "state" / "device_codes.txt", "a", encoding="utf-8") as fh:
            fh.write(f"{provider} ({conn_id[:8]}): code={user_code}  url={verification_uri}\n")
    except Exception:
        pass
    log(f"[{provider}] Expires in {expires_in}s. Polling for completion...")
    
    # Poll for up to 10 minutes
    interval = data.get("interval", 5)
    max_attempts = min(120, expires_in // max(interval, 1))
    
    for attempt in range(max_attempts):
        time.sleep(interval)
        poll_r = session.post(
            f"{OMNI_BASE}/api/oauth/{provider}/device-poll",
            json={"connectionId": conn_id, "device_code": "[PRESENT]"},  # server has it from state
            timeout=30,
        )
        poll_data = poll_r.json() if poll_r.ok or poll_r.status_code in (200, 400) else {}
        
        if poll_data.get("success"):
            log(f"[{provider}] Device code flow SUCCESSFUL")
            return {"success": True, "method": "device_code"}
        
        if poll_data.get("error") and not poll_data.get("pending"):
            err = poll_data.get("error", "unknown")
            if "authorization_pending" in str(err) or "slow_down" in str(err):
                continue  # still waiting
            return {"success": False, "error": f"device-code poll error: {err}"}
        
        if attempt % 6 == 0:
            log(f"[{provider}] Still waiting for device code... ({attempt * interval}s elapsed). Code: {user_code} at {verification_uri}")
    
    return {"success": False, "error": f"device-code timeout after {max_attempts * interval}s"}

# ─── Check existing connections that are actually working (from live API) ─────
def check_current_status(session: requests.Session, target_ids: list[str]) -> dict:
    """Return current status of each connection from the live API."""
    r = session.get(f"{OMNI_BASE}/api/providers")
    if not r.ok:
        return {}
    connections = r.json().get("connections", [])
    return {c["id"]: c for c in connections if c["id"] in target_ids}

# ─── Try API refresh first ────────────────────────────────────────────────────
def try_api_refresh(session: requests.Session, conn_id: str, provider: str) -> Optional[dict]:
    """Attempt token refresh via API. Returns result if successful, None if needs browser."""
    try:
        r = session.post(f"{OMNI_BASE}/api/providers/{conn_id}/refresh", timeout=30)
        data = r.json()
        if data.get("success"):
            log(f"[{provider}/{conn_id[:8]}] API refresh SUCCEEDED")
            return {"success": True, "method": "api_refresh"}
        log(f"[{provider}/{conn_id[:8]}] API refresh failed: {data.get('error', 'unknown')} — need browser")
        return None
    except Exception as e:
        log(f"[{provider}/{conn_id[:8]}] API refresh exception: {e}")
        return None

# ─── Playwright Google OAuth flow ────────────────────────────────────────────
async def run_google_oauth_flow(
    page,
    session: requests.Session,
    conn_id: str,
    provider: str,
    google_email: str,
) -> dict:
    """
    Full Google OAuth flow using OmniRoute's /authorize + /callback + /exchange.
    Uses the existing Chrome session (connected via CDP).
    """
    
    # Step 1: Get authorize URL from OmniRoute, then inject login_hint so Google
    # goes directly to the right account without the account picker.
    redirect_uri = f"http://127.0.0.1:20128/callback"
    r = session.get(
        f"{OMNI_BASE}/api/oauth/{provider}/authorize",
        params={"redirect_uri": redirect_uri, "connectionId": conn_id},
        timeout=15,
    )
    if not r.ok:
        return {"success": False, "error": f"authorize failed: {r.status_code}"}

    auth_data = r.json()
    auth_url = auth_data.get("authUrl")
    code_verifier = auth_data.get("codeVerifier")
    actual_redirect_uri = auth_data.get("redirectUri", redirect_uri)

    if not auth_url:
        return {"success": False, "error": "No authUrl returned"}

    # Inject login_hint + authuser to skip account picker entirely
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    parsed = urlparse(auth_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["login_hint"] = [google_email]
    qs["prompt"] = ["consent"]  # force fresh consent screen, skip picker
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    auth_url = urlunparse(parsed._replace(query=new_query))

    log(f"[{provider}] Opening Google OAuth for {google_email} (login_hint injected)...")

    # Step 2: Navigate to Google OAuth URL — should go straight to consent, no picker
    await page.goto(auth_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    current_url = page.url
    log(f"[{provider}] URL after goto: {current_url[:80]}")
    
    # Step 3: Handle Google account picker / sign-in
    # Check if we're on Google account picker
    if "accounts.google.com" in current_url:
        # Look for the account matching google_email
        try:
            email_link = page.get_by_text(google_email, exact=False)
            count = await email_link.count()
            if count > 0:
                log(f"[{provider}] Found account {google_email} in picker, clicking...")
                await email_link.first.click()
                await page.wait_for_timeout(3000)
            else:
                other_account = page.get_by_text("Use another account", exact=False)
                if await other_account.count() > 0:
                    log(f"[{provider}] Clicking 'Use another account'...")
                    await other_account.first.click()
                    await page.wait_for_timeout(2000)
                    email_input = page.get_by_label("Email or phone", exact=False)
                    if await email_input.count() > 0:
                        await email_input.first.fill(google_email)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(2000)
                else:
                    log(f"[{provider}] WARNING: Could not find {google_email} in account picker")
        except Exception as e:
            log(f"[{provider}] Account picker interaction error: {e}")
    
    # Step 4: Handle consent/permission/nativeapp screens — keep clicking through until redirect
    for _attempt in range(10):
        await page.wait_for_timeout(2000)
        current_url = page.url
        if "callback" in current_url or "code=" in current_url:
            break
        if "accounts.google.com" not in current_url:
            break
        try:
            clicked = False
            for btn_text in ["Continue", "Allow", "Confirm", "Next", "Sign in"]:
                btn = page.get_by_role("button", name=re.compile(btn_text, re.I))
                if await btn.count() > 0:
                    log(f"[{provider}] Clicking '{btn_text}' on Google screen...")
                    await btn.first.click()
                    clicked = True
                    break
            if not clicked:
                # Try any visible primary action button
                btn = page.locator("button[type=submit], input[type=submit]")
                if await btn.count() > 0:
                    log(f"[{provider}] Clicking submit button...")
                    await btn.first.click()
        except Exception as e:
            log(f"[{provider}] Consent interaction error: {e}")
            break
    
    # Step 5: Wait for callback redirect
    # Wait for URL to change to localhost:20128/callback
    max_wait = 30
    for i in range(max_wait):
        await page.wait_for_timeout(1000)
        current_url = page.url
        if "callback" in current_url and ("code=" in current_url or "localhost" in current_url):
            break
        if "20128/callback" in current_url or "127.0.0.1:20128/callback" in current_url:
            break
        if i % 5 == 0:
            log(f"[{provider}] Waiting for callback redirect ({i}s)... URL: {current_url[:80]}")
    
    current_url = page.url
    
    # Step 6: Extract code and state from callback URL
    if "callback" not in current_url:
        page_content = await page.content()
        log(f"[{provider}] Did not reach callback URL. Current: {current_url[:80]}")
        
        # Try to find code in URL params anyway
        if "code=" not in current_url:
            return {"success": False, "error": f"Did not reach callback URL: {current_url[:80]}"}
    
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(current_url)
    params = parse_qs(parsed.query)
    
    code = params.get("code", [None])[0]
    returned_state = params.get("state", [None])[0]
    
    if not code:
        return {"success": False, "error": f"No code in callback URL: {current_url[:80]}"}
    
    log(f"[{provider}] Got authorization code, calling exchange...")
    
    # Step 7: Call exchange endpoint
    exchange_r = session.post(
        f"{OMNI_BASE}/api/oauth/{provider}/exchange",
        json={
            "code": code,
            "redirectUri": actual_redirect_uri,
            "connectionId": conn_id,
            "codeVerifier": code_verifier,
            **({"state": returned_state} if returned_state else {}),
        },
        timeout=30,
    )
    
    exchange_data = exchange_r.json()
    if exchange_r.ok and (exchange_data.get("success") or exchange_data.get("connectionId")):
        log(f"[{provider}/{conn_id[:8]}] Exchange SUCCESSFUL")
        # Activate the connection
        session.put(f"{OMNI_BASE}/api/providers/{conn_id}", json={"isActive": True})
        return {"success": True, "method": "google_oauth"}
    else:
        return {"success": False, "error": f"Exchange failed: {exchange_data.get('error', str(exchange_data)[:100])}"}


# ─── PKCE callback server flow (codex/xai-oauth/grok-cli) ───────────────────
async def run_pkce_callback_flow(
    page,
    session: requests.Session,
    conn_id: str,
    provider: str,
) -> dict:
    """
    PKCE flow using /api/oauth/{provider}/start-callback-server and poll-callback.
    """
    # Step 1: Start callback server
    r = session.post(
        f"{OMNI_BASE}/api/oauth/{provider}/start-callback-server",
        json={"connectionId": conn_id},
        timeout=30,
    )
    if not r.ok:
        return {"success": False, "error": f"start-callback-server failed: {r.status_code} {r.text[:100]}"}
    
    server_data = r.json()
    auth_url = server_data.get("authUrl")
    
    if not auth_url:
        return {"success": False, "error": "No authUrl from start-callback-server"}
    
    log(f"[{provider}] Opening PKCE OAuth window...")
    
    # Step 2: Open auth URL in a new tab
    popup = await page.playwright.evaluate(f"window.open('{auth_url}', 'oauth_auth', 'width=600,height=700')")
    
    # Step 3: Poll for completion (the callback server handles the code exchange)
    log(f"[{provider}] Polling for callback completion...")
    for attempt in range(75):  # 150 seconds
        await page.wait_for_timeout(2000)
        poll_r = session.post(
            f"{OMNI_BASE}/api/oauth/{provider}/poll-callback",
            json={"connectionId": conn_id},
            timeout=15,
        )
        poll_data = poll_r.json() if poll_r.content else {}
        
        if poll_data.get("success"):
            log(f"[{provider}/{conn_id[:8]}] PKCE callback SUCCESSFUL")
            session.put(f"{OMNI_BASE}/api/providers/{conn_id}", json={"isActive": True})
            return {"success": True, "method": "pkce_callback"}
        
        if poll_data.get("error") and not poll_data.get("pending"):
            return {"success": False, "error": f"poll-callback error: {poll_data.get('error')}"}
        
        if attempt % 5 == 0:
            log(f"[{provider}] Still waiting for PKCE callback ({attempt * 2}s)...")
    
    return {"success": False, "error": "PKCE callback timeout after 150s"}


# ─── Browser OAuth flow (cline, etc.) ───────────────────────────────────────
async def run_browser_oauth_flow(
    page,
    session: requests.Session,
    conn_id: str,
    provider: str,
) -> dict:
    """Generic browser OAuth flow for providers like cline."""
    redirect_uri = f"http://127.0.0.1:20128/callback"
    r = session.get(
        f"{OMNI_BASE}/api/oauth/{provider}/authorize",
        params={"redirect_uri": redirect_uri, "connectionId": conn_id},
        timeout=15,
    )
    if not r.ok:
        return {"success": False, "error": f"authorize failed: {r.status_code}"}
    
    auth_data = r.json()
    auth_url = auth_data.get("authUrl")
    code_verifier = auth_data.get("codeVerifier")
    actual_redirect_uri = auth_data.get("redirectUri", redirect_uri)
    
    if not auth_url:
        return {"success": False, "error": "No authUrl returned"}
    
    log(f"[{provider}] Opening browser OAuth flow...")
    await page.goto(auth_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    
    # Wait for callback redirect (up to 60 seconds)
    for i in range(60):
        await page.wait_for_timeout(1000)
        current_url = page.url
        if "callback" in current_url and "code=" in current_url:
            break
        if i % 10 == 0 and i > 0:
            log(f"[{provider}] Waiting for OAuth completion ({i}s)... URL: {current_url[:60]}")
    
    current_url = page.url
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(current_url)
    params = parse_qs(parsed.query)
    
    code = params.get("code", [None])[0]
    returned_state = params.get("state", [None])[0]
    
    if not code:
        # Check if we're on a page showing a code to paste
        log(f"[{provider}] URL: {current_url[:80]}")
        content = await page.content()
        # Look for auth code in page content
        code_match = re.search(r'\b([A-Za-z0-9_-]{16,})\b', content[:2000])
        if code_match:
            log(f"[{provider}] Found potential code in page content")
        return {"success": False, "error": f"No code in callback URL: {current_url[:80]}", "blocker": "manual_required"}
    
    exchange_r = session.post(
        f"{OMNI_BASE}/api/oauth/{provider}/exchange",
        json={
            "code": code,
            "redirectUri": actual_redirect_uri,
            "connectionId": conn_id,
            **({"codeVerifier": code_verifier} if code_verifier else {}),
            **({"state": returned_state} if returned_state else {}),
        },
        timeout=30,
    )
    exchange_data = exchange_r.json()
    if exchange_r.ok and (exchange_data.get("success") or exchange_data.get("connectionId")):
        log(f"[{provider}/{conn_id[:8]}] Exchange SUCCESSFUL")
        session.put(f"{OMNI_BASE}/api/providers/{conn_id}", json={"isActive": True})
        return {"success": True, "method": "browser_oauth"}
    else:
        return {"success": False, "error": f"Exchange failed: {exchange_data.get('error', str(exchange_data)[:100])}"}


# ─── Main orchestrator ───────────────────────────────────────────────────────
async def main():
    from playwright.async_api import async_playwright
    
    log("=== OmniRoute OAuth Re-Authentication Script ===")
    log(f"Browser profile: {BROWSER_PROFILE}")
    
    session = get_api_session()
    log("OmniRoute API login OK")
    
    results = {}
    device_code_results = {}
    
    # ── Pass 1: Try API refresh for everything first ──────────────────────────
    log("\n--- Pass 1: API refresh attempt for all connections ---")
    for conn_id, provider, name, method, google_email in PROVIDERS_TO_REAUTH:
        label = f"{provider}/{name or 'N/A'}"
        result = try_api_refresh(session, conn_id, provider)
        if result:
            results[conn_id] = {**result, "label": label}
    
    # ── Pass 2: Device code flows (no browser popup needed for these) ─────────
    log("\n--- Pass 2: Device code flows ---")
    device_code_providers = [(c, p, n, m, g) for c, p, n, m, g in PROVIDERS_TO_REAUTH 
                              if m == "device_code" and c not in results]
    
    for conn_id, provider, name, method, google_email in device_code_providers:
        label = f"{provider}/{name or 'N/A'}"
        log(f"\n[{label}] Starting device code flow...")
        result = handle_device_code(session, conn_id, provider)
        results[conn_id] = {**result, "label": label, "method": "device_code"}
        if result.get("success"):
            session.put(f"{OMNI_BASE}/api/providers/{conn_id}", json={"isActive": True})
    
    # ── Pass 3: Browser OAuth flows ───────────────────────────────────────────
    browser_providers = [(c, p, n, m, g) for c, p, n, m, g in PROVIDERS_TO_REAUTH
                         if m in ("google_oauth", "browser_oauth", "pkce_callback")
                         and c not in results]
    
    if not browser_providers:
        log("\nNo browser OAuth flows needed.")
    else:
        log(f"\n--- Pass 3: Browser OAuth flows ({len(browser_providers)} providers) ---")
        log(f"Connecting to existing Chrome on CDP {CDP_URL} (all Google accounts already logged in)...")

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()

            # Inject OmniRoute auth cookie
            cookies_to_inject = [{"name": c.name, "value": c.value, "domain": "localhost", "path": "/"} for c in session.cookies]
            if cookies_to_inject:
                await context.add_cookies(cookies_to_inject)

            for conn_id, provider, name, method, google_email in browser_providers:
                label = f"{provider}/{name or 'N/A'}"
                log(f"\n=== {label} [{conn_id[:8]}] via {method} (account: {google_email}) ===")

                # Fresh tab per provider — no cross-account state
                page = await context.new_page()
                try:
                    if method == "google_oauth":
                        result = await run_google_oauth_flow(page, session, conn_id, provider, google_email)
                    elif method == "pkce_callback":
                        result = await run_pkce_callback_flow(page, session, conn_id, provider)
                    elif method == "browser_oauth":
                        result = await run_browser_oauth_flow(page, session, conn_id, provider)
                    else:
                        result = {"success": False, "error": f"Unknown method: {method}"}

                    results[conn_id] = {**result, "label": label}
                    if result.get("success"):
                        log(f"[{label}] SUCCESS via {result.get('method', method)}")
                    else:
                        log(f"[{label}] FAILED: {result.get('error', 'unknown')}")
                except Exception as e:
                    log(f"[{label}] EXCEPTION: {e}")
                    results[conn_id] = {"success": False, "error": str(e), "label": label}
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass
    
    # ── Pass 4: import_token providers (windsurf/trae — manual required) ──────
    log("\n--- Pass 4: Import-token providers (windsurf/trae) ---")
    for conn_id, provider, name, method, _ in PROVIDERS_TO_REAUTH:
        if method != "import_token" or conn_id in results:
            continue
        label = f"{provider}/{name or 'N/A'}"
        log(f"[{label}] BLOCKED: {provider} requires manual token import.")
        if provider == "windsurf":
            log(f"  -> In Windsurf/VS Code IDE, run 'Windsurf: Provide Auth Token' command, copy token, then call:")
            log(f"     POST /api/oauth/windsurf/import-token with {{token: '<ws-...>', connectionId: '{conn_id}'}}")
        elif provider == "trae":
            log(f"  -> Sign into solo.trae.ai, check DevTools Network for Cloud-IDE-JWT header, then call:")
            log(f"     POST /api/oauth/trae/import with {{accessToken: '<jwt>', connectionId: '{conn_id}'}}")
        results[conn_id] = {"success": False, "error": "manual_import_required", "label": label, "blocked": True}
    
    # ── Summary ───────────────────────────────────────────────────────────────
    log("\n" + "=" * 60)
    log("RESULTS SUMMARY")
    log("=" * 60)
    
    succeeded = [(k, v) for k, v in results.items() if v.get("success")]
    failed = [(k, v) for k, v in results.items() if not v.get("success")]
    
    log(f"SUCCESS: {len(succeeded)}/{len(results)}")
    for conn_id, v in succeeded:
        log(f"  OK  {v['label']} [{conn_id[:8]}] via {v.get('method', '?')}")
    
    log(f"\nFAILED/BLOCKED: {len(failed)}")
    for conn_id, v in failed:
        err = v.get("error", "unknown")
        blocked = " [BLOCKED-manual]" if v.get("blocked") else ""
        log(f"  FAIL {v['label']} [{conn_id[:8]}]: {err}{blocked}")
    
    # Save results (no secrets)
    safe_results = {}
    for k, v in results.items():
        safe_results[k] = {kk: vv for kk, vv in v.items() 
                           if not SECRET_PATTERNS.search(kk)}
    
    RESULTS_FILE.write_text(json.dumps(safe_results, indent=2), encoding="utf-8")
    log(f"\nResults saved to: {RESULTS_FILE}")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
