#!/usr/bin/env python3
"""
Single-provider OAuth re-authentication runner with visual & DOM diagnosis.
Following Rule 11 (Visual Assessment -> DOM Diagnosis -> Post-Action Verification)
and Rule 12 (Chrome Profile Isolation).
"""
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact
from password_vault import retrieve_password

OMNI_BASE = "http://localhost:20128"
CDP_URL = "http://127.0.0.1:9222"
SCREENSHOT_DIR = PROJECT_ROOT / "state" / "reauth_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def get_api_session() -> requests.Session:
    pw = retrieve_password(PROJECT_ROOT / "state" / "omniroute_password.bin")
    session = requests.Session()
    r = session.post(f"{OMNI_BASE}/api/auth/login", json={"password": pw})
    assert r.status_code == 200, f"Login failed: {r.status_code}"
    return session


async def reauth_google_oauth(page, session: requests.Session, conn_id: str, provider: str, target_email: str) -> bool:
    redirect_uri = f"http://127.0.0.1:20128/callback"
    r = session.get(
        f"{OMNI_BASE}/api/oauth/{provider}/authorize",
        params={"redirect_uri": redirect_uri, "connectionId": conn_id},
        timeout=15,
    )
    if not r.ok:
        print(f"[-] Authorize failed: {r.status_code}")
        return False

    auth_data = r.json()
    auth_url = auth_data.get("authUrl")
    code_verifier = auth_data.get("codeVerifier")
    actual_redirect_uri = auth_data.get("redirectUri", redirect_uri)

    if not auth_url:
        print("[-] No authUrl returned")
        return False

    print(f"[*] Navigating to Google OAuth URL...")
    await page.goto(auth_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # RULE 11 STEP 1: VISUAL ASSESSMENT
    snap1_path = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_1_initial.png"
    await page.screenshot(path=str(snap1_path))
    print(f"[+] Screenshot 1 (Visual Assessment) saved to: {snap1_path}")
    print(f"    Current URL: {page.url[:100]}")

    # RULE 11 STEP 2: DOM DIAGNOSIS
    current_url = page.url
    if "accounts.google.com" in current_url:
        print("[*] On Google Accounts domain — running DOM diagnosis...")

        email_el = page.get_by_text(target_email, exact=False)
        if await email_el.count() > 0:
            print(f"[+] DOM Diagnosis: Found target email {target_email} on screen. Clicking...")
            await email_el.first.click()
            await page.wait_for_timeout(3000)

            # RULE 11 STEP 3: POST-ACTION VERIFICATION
            snap2_path = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_2_after_click_email.png"
            await page.screenshot(path=str(snap2_path))
            print(f"[+] Screenshot 2 (Post-Action Verification) saved: {snap2_path}")

    # Consent buttons loop
    for _ in range(5):
        await page.wait_for_timeout(2000)
        current_url = page.url
        if "callback" in current_url or "code=" in current_url:
            print(f"[+] Callback URL reached!")
            break
        if "accounts.google.com" in current_url:
            for btn_text in ["Continue", "Allow", "Confirm", "Next", "Sign in"]:
                btn = page.get_by_role("button", name=re.compile(btn_text, re.I))
                if await btn.count() > 0:
                    print(f"[+] DOM Diagnosis: Found button '{btn_text}'. Clicking...")
                    await btn.first.click()
                    await page.wait_for_timeout(3000)
                    snap_btn_path = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_btn_{btn_text}.png"
                    await page.screenshot(path=str(snap_btn_path))
                    print(f"[+] Screenshot (Post-Action Verification) saved: {snap_btn_path}")
                    break

    current_url = page.url
    if "code=" in current_url:
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        returned_state = params.get("state", [None])[0]
        if code:
            print(f"[+] Captured OAuth code, exchanging with OmniRoute API...")
            ex_resp = session.post(
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
            if ex_resp.ok and (ex_resp.json().get("success") or ex_resp.json().get("connectionId")):
                print(f"[SUCCESS] {provider} ({target_email}) re-authenticated & active!")
                session.put(f"{OMNI_BASE}/api/providers/{conn_id}", json={"isActive": True})
                return True
            else:
                print(f"[-] Exchange response: {ex_resp.text[:150]}")

    snap_final = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_final.png"
    await page.screenshot(path=str(snap_final))
    print(f"[!] Flow ended without code. Final screenshot: {snap_final}")
    return False


async def reauth_pkce_callback(page, session: requests.Session, conn_id: str, provider: str, target_email: str) -> bool:
    print(f"[*] Starting PKCE callback server for {provider}...")
    r = session.post(
        f"{OMNI_BASE}/api/oauth/{provider}/start-callback-server",
        json={"connectionId": conn_id},
        timeout=30,
    )
    if not r.ok:
        print(f"[-] start-callback-server failed: {r.status_code} {r.text[:100]}")
        return False

    server_data = r.json()
    auth_url = server_data.get("authUrl")
    if not auth_url:
        print("[-] No authUrl returned")
        return False

    print(f"[*] Navigating to PKCE auth URL...")
    await page.goto(auth_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # RULE 11 STEP 1: VISUAL ASSESSMENT
    snap1 = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_1_pkce_initial.png"
    await page.screenshot(path=str(snap1))
    print(f"[+] Screenshot 1 (Visual Assessment) saved: {snap1}")
    print(f"    URL: {page.url[:100]}")

    # RULE 11 STEP 2: DOM DIAGNOSIS
    current_url = page.url
    if target_email and "accounts.google.com" in current_url:
        email_el = page.get_by_text(target_email, exact=False)
        if await email_el.count() > 0:
            print(f"[+] DOM Diagnosis: Clicking email {target_email}...")
            await email_el.first.click()
            await page.wait_for_timeout(3000)
            snap2 = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_2_pkce_after_email.png"
            await page.screenshot(path=str(snap2))
            print(f"[+] Screenshot 2 saved: {snap2}")

    # Poll callback server
    print(f"[*] Polling PKCE callback server for completion...")
    for attempt in range(40):
        await page.wait_for_timeout(2000)
        poll_r = session.post(
            f"{OMNI_BASE}/api/oauth/{provider}/poll-callback",
            json={"connectionId": conn_id},
            timeout=15,
        )
        poll_data = poll_r.json() if poll_r.content else {}
        if poll_data.get("success"):
            print(f"[SUCCESS] {provider} PKCE callback server completed!")
            session.put(f"{OMNI_BASE}/api/providers/{conn_id}", json={"isActive": True})
            return True
        if attempt % 5 == 0:
            print(f"    Waiting for PKCE callback... ({attempt * 2}s)")

    snap_final = SCREENSHOT_DIR / f"{provider}_{conn_id[:8]}_pkce_final.png"
    await page.screenshot(path=str(snap_final))
    print(f"[!] PKCE callback timed out. Final screenshot: {snap_final}")
    return False


async def main():
    if len(sys.argv) < 5:
        print("Usage: python run_single_reauth.py <conn_id> <provider> <method> <email>")
        sys.exit(1)

    conn_id = sys.argv[1]
    provider = sys.argv[2]
    method = sys.argv[3]
    email = sys.argv[4]

    print(f"\n========================================================")
    print(f"RE-AUTHENTICATING: {provider} ({email}) [{conn_id[:8]}] via {method}")
    print(f"========================================================")

    session = get_api_session()

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        cookies = [{"name": c.name, "value": c.value, "domain": "localhost", "path": "/"} for c in session.cookies]
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        try:
            if method == "google_oauth":
                ok = await reauth_google_oauth(page, session, conn_id, provider, email)
            elif method == "pkce_callback":
                ok = await reauth_pkce_callback(page, session, conn_id, provider, email)
            else:
                print(f"Unknown method: {method}")
                ok = False
        finally:
            await page.close()


if __name__ == "__main__":
    asyncio.run(main())
