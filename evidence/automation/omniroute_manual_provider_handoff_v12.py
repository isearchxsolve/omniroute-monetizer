#!/usr/bin/env python3
"""
OmniRoute Manual Provider Handoff v12

Purpose
-------
Open one real OmniRoute provider screen and then STOP. The operator performs
reauthentication/import/save/test manually.

This script is observational/navigation only. It does NOT click provider
controls and does NOT call provider mutation endpoints.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if BASE_URL.endswith("/v1"):
    BASE_URL = BASE_URL[:-3].rstrip("/")
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "")
HOLD_SECONDS = max(300, int(os.environ.get("OMNIROUTE_HANDOFF_HOLD_SECONDS", "3600")))
OUT = Path(os.environ.get("OMNIROUTE_HANDOFF_DIR", "omniroute_manual_handoff"))

# Route aliases observed from the user's OmniRoute UI bundle.
ROUTE_ALIASES = {
    "opencode": "opencode-go",
}


def log(message: str) -> None:
    print(message, flush=True)


def provider_arg() -> str:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return sys.argv[1].strip()
    print("\nEnter the provider slug exactly as shown by OmniRoute.")
    value = input("Provider: ").strip()
    if not value:
        raise SystemExit("No provider supplied.")
    return value


def visible_body(page) -> str:
    try:
        return (page.locator("body").inner_text() or "")[:10000]
    except Exception:
        return ""


def ensure_dashboard(page) -> None:
    """Login if needed, then verify we are genuinely on the dashboard."""
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1200)

    password_field = page.locator('input[type="password"]').first
    if password_field.count() and password_field.is_visible():
        if not PASSWORD:
            raise RuntimeError(
                "OMNIROUTE_PASSWORD is not set. Use the PowerShell runner so it "
                "can securely prompt for the password."
            )
        password_field.fill(PASSWORD)
        password_field.press("Enter")
        page.wait_for_timeout(2500)

    # The UI may land at /, /home, or /dashboard depending on the build.
    url = page.url
    body = visible_body(page).lower()
    still_login = False
    try:
        still_login = page.locator('input[type="password"]').first.is_visible()
    except Exception:
        pass

    dashboard_markers = (
        "/dashboard" in url.lower()
        or "/home" in url.lower()
        or "providers" in body
        or "discovery" in body
    )
    if still_login or not dashboard_markers:
        raise RuntimeError(
            f"OmniRoute login did not reach the dashboard. URL={url!r}; "
            f"body={body[:500]!r}"
        )


def find_provider_link(page, provider: str) -> Optional[str]:
    """Find an actual provider href from the providers page without clicking it."""
    page.goto(f"{BASE_URL}/dashboard/providers", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1200)
    wanted = provider.lower().strip()
    links = page.locator('a[href*="/dashboard/providers/"]')
    for i in range(links.count()):
        link = links.nth(i)
        try:
            href = link.get_attribute("href") or ""
            text = (link.inner_text() or "").strip().lower()
            aria = (link.get_attribute("aria-label") or "").lower()
            title = (link.get_attribute("title") or "").lower()
            hay = " ".join((text, aria, title, href.lower()))
            if wanted == text or wanted in hay:
                return href
        except Exception:
            continue
    return None


def open_provider(page, provider: str) -> str:
    """Open the provider detail page, with a safe fallback to the live href."""
    slug = ROUTE_ALIASES.get(provider.lower(), provider)
    direct = f"{BASE_URL}/dashboard/providers/{slug}"

    response = page.goto(direct, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1200)
    status = response.status if response is not None else None

    # Direct route is preferred, but do not leave the user on a silent 404.
    body = visible_body(page)
    lower = body.lower()
    if status is not None and status >= 400 or "404" in lower and "not found" in lower:
        href = find_provider_link(page, provider)
        if href:
            if href.startswith("http://") or href.startswith("https://"):
                target = href
            elif href.startswith("/"):
                target = BASE_URL + href
            else:
                target = BASE_URL + "/" + href
            page.goto(target, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1200)
            return page.url
        raise RuntimeError(
            f"Provider page not found for {provider!r}. Direct route returned HTTP {status}."
        )

    # Make sure the destination actually looks like a provider page.
    body = visible_body(page).lower()
    provider_marker = provider.lower().replace("-", " ")
    if provider_marker not in body and slug.lower().replace("-", " ") not in body:
        # We still allow the route if it is clearly a provider detail URL and not the dashboard/login.
        if "/dashboard/providers/" not in page.url.lower():
            raise RuntimeError(
                f"Unexpected destination after opening {provider!r}: {page.url}"
            )
    return page.url


def main() -> int:
    provider = provider_arg()
    OUT.mkdir(parents=True, exist_ok=True)

    log("=" * 72)
    log("OmniRoute MANUAL PROVIDER HANDOFF v12")
    log("Navigation only — operator performs provider actions")
    log("=" * 72)
    log(f"Base URL : {BASE_URL}")
    log(f"Provider : {provider}")
    log("")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        # Navigation only. No provider mutation calls or control clicks.
        ensure_dashboard(page)
        log(f"[+] Logged into dashboard: {page.url}")

        target_url = open_provider(page, provider)
        screenshot = OUT / f"{provider.replace('/', '_')}_opened.png"
        page.screenshot(path=str(screenshot), full_page=True)

        log(f"[+] Provider screen opened: {target_url}")
        log(f"[+] Screenshot: {screenshot}")
        log("")
        log("==================== YOUR TURN ====================")
        log("The script will NOT click Re-authenticate, Save, Test, Import,")
        log("Refresh, Disable, Connect, or any other provider control.")
        log("You now have full control of the visible browser.")
        log("Close the browser when you are finished.")
        log("===================================================")

        deadline = time.time() + HOLD_SECONDS
        while time.time() < deadline:
            if page.is_closed():
                break
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break

        try:
            context.close()
            browser.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
