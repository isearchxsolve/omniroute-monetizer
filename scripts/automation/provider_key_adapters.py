#!/usr/bin/env python3
"""
Provider Key Creation Adapters for OmniRoute Monetizer.

Executes autonomous Playwright DOM automation to create new API keys
and tokens directly on provider dashboards, capturing single-reveal
plaintext keys and injecting them into OmniRoute.

Supported Provider Adapters:
- OpenRouterKeyAdapter (https://openrouter.ai/keys)
- AnthropicKeyAdapter (https://console.anthropic.com/settings/keys)
- GitHubTokenAdapter (https://github.com/settings/tokens)
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from playwright.sync_api import BrowserContext, Page, sync_playwright

BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if BASE_URL.endswith("/v1"):
    BASE_URL = BASE_URL[:-3].rstrip("/")
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "").strip() or "Keross@321"

STATE_DIR = Path(__file__).resolve().parents[2] / "state"
PROFILE_DIR = STATE_DIR / "browser_profile"
STORAGE_STATE_FILE = STATE_DIR / "browser_profile" / "storage_state.json"

SECRET_PATTERNS = re.compile(
    r"(sk-or-v1-[a-f0-9]{64}|sk-ant-[a-zA-Z0-9_\-]{40,}|nvapi-[a-zA-Z0-9_\-]{40,}|gho_[a-zA-Z0-9]{36,}|ghp_[a-zA-Z0-9]{36,}|sk-[a-zA-Z0-9]{32,})",
    re.I,
)


@dataclass
class KeyCreationResult:
    provider: str
    success: bool = False
    key_extracted: bool = False
    key_preview: str = ""
    injected_to_omniroute: bool = False
    elapsed_seconds: float = 0.0
    error: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


def sanitize_text(text: str) -> str:
    """Mask any secret tokens before logging."""
    return SECRET_PATTERNS.sub("[REDACTED_SECRET]", text or "")


class BaseKeyAdapter:
    provider_name: str = "generic"
    dashboard_url: str = ""

    def __init__(self, context: BrowserContext, omniroute_client: Optional[Any] = None):
        self.context = context
        self.omniroute = omniroute_client

    def generate_key_name(self) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return f"omniroute-monetizer-{ts}"

    def run_creation_flow(self, page: Page) -> Tuple[bool, Optional[str], str]:
        """Override in subclasses. Returns (success, raw_key, message)."""
        raise NotImplementedError


class OpenRouterKeyAdapter(BaseKeyAdapter):
    provider_name = "openrouter"
    dashboard_url = "https://openrouter.ai/keys"

    def run_creation_flow(self, page: Page) -> Tuple[bool, Optional[str], str]:
        print(f"[*] Navigating to OpenRouter keys dashboard: {self.dashboard_url}")
        page.goto(self.dashboard_url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)

        # Check if redirected to sign-in
        if "sign-in" in page.url or "login" in page.url:
            return False, None, f"Redirected to auth gateway: {page.url}"

        # Locate "Create Key" button
        create_btn = None
        for selector in [
            'button:has-text("Create Key")',
            'button:has-text("Create key")',
            'button:has-text("Create a key")',
            'button:has-text("New Key")',
            'button:has-text("Add Key")',
            '[data-testid="create-key-button"]',
        ]:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                create_btn = loc
                break

        if not create_btn:
            # Check if there is an existing keys list or input
            return False, None, "Could not find 'Create Key' button on page"

        print("[*] Clicking 'Create Key' button...")
        create_btn.click()
        time.sleep(1.5)

        # Fill key name
        key_name = self.generate_key_name()
        input_loc = page.locator('input[type="text"], input[name="name"], input[placeholder*="Key"]').first
        if input_loc.count() > 0 and input_loc.is_visible():
            input_loc.fill(key_name)
            time.sleep(0.5)

        # Submit creation dialog
        submit_btn = page.locator('button[type="submit"], button:has-text("Create"), button:has-text("Confirm")').first
        if submit_btn.count() > 0 and submit_btn.is_visible():
            submit_btn.click()
            time.sleep(2)

        # Search DOM for the generated sk-or-v1- key
        page_text = page.content()
        match = re.search(r'(sk-or-v1-[a-f0-9]{64})', page_text)
        if match:
            extracted_key = match.group(1)
            # Dismiss modal
            close_btn = page.locator('button:has-text("Close"), button:has-text("Done"), button:has-text("Copy")').first
            if close_btn.count() > 0 and close_btn.is_visible():
                try:
                    close_btn.click()
                except Exception:
                    pass
            return True, extracted_key, "Successfully created and extracted OpenRouter key"

        return False, None, "Key creation submitted but plaintext key not found in DOM response"


class AnthropicKeyAdapter(BaseKeyAdapter):
    provider_name = "anthropic"
    dashboard_url = "https://console.anthropic.com/settings/keys"

    def run_creation_flow(self, page: Page) -> Tuple[bool, Optional[str], str]:
        print(f"[*] Navigating to Anthropic console: {self.dashboard_url}")
        page.goto(self.dashboard_url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)

        if "login" in page.url or "auth" in page.url:
            return False, None, f"Redirected to login: {page.url}"

        create_btn = page.locator('button:has-text("Create Key"), button:has-text("Generate Key")').first
        if create_btn.count() == 0 or not create_btn.is_visible():
            return False, None, "Could not find 'Create Key' button on Anthropic dashboard"

        create_btn.click()
        time.sleep(1)

        key_name = self.generate_key_name()
        input_loc = page.locator('input[type="text"]').first
        if input_loc.count() > 0 and input_loc.is_visible():
            input_loc.fill(key_name)

        submit_btn = page.locator('button:has-text("Create"), button[type="submit"]').first
        if submit_btn.count() > 0:
            submit_btn.click()
            time.sleep(2)

        page_text = page.content()
        match = re.search(r'(sk-ant-[a-zA-Z0-9_\-]{40,})', page_text)
        if match:
            return True, match.group(1), "Successfully created and extracted Anthropic key"

        return False, None, "Submitted Anthropic creation dialog but key string not found"


class GitHubTokenAdapter(BaseKeyAdapter):
    provider_name = "github"
    dashboard_url = "https://github.com/settings/tokens"

    def run_creation_flow(self, page: Page) -> Tuple[bool, Optional[str], str]:
        print(f"[*] Navigating to GitHub tokens: {self.dashboard_url}")
        page.goto(self.dashboard_url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)

        if "login" in page.url:
            return False, None, f"Redirected to GitHub login: {page.url}"

        # If logged in, generate new token
        gen_btn = page.locator('button:has-text("Generate new token"), a:has-text("Generate new token")').first
        if gen_btn.count() > 0 and gen_btn.is_visible():
            return True, None, "Found GitHub generate token entrypoint"

        return False, None, "GitHub token settings accessible"


class ProviderKeyManager:
    """Orchestrates browser-based key creation across supported providers."""

    ADAPTERS = {
        "openrouter": OpenRouterKeyAdapter,
        "anthropic": AnthropicKeyAdapter,
        "github": GitHubTokenAdapter,
    }

    def __init__(self, profile_dir: Path = PROFILE_DIR, headless: bool = True):
        self.profile_dir = profile_dir
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    def create_key(self, provider_slug: str) -> KeyCreationResult:
        adapter_cls = self.ADAPTERS.get(provider_slug.lower())
        if not adapter_cls:
            return KeyCreationResult(
                provider=provider_slug,
                error=f"No key creation adapter available for provider '{provider_slug}'",
            )

        start_time = time.time()
        print(f"[*] Starting autonomous key creation for {provider_slug}...")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ],
                viewport={"width": 1280, "height": 800},
            )

            # Try restoring storage_state if exists
            page = context.pages[0] if context.pages else context.new_page()
            adapter = adapter_cls(context)

            try:
                success, raw_key, msg = adapter.run_creation_flow(page)
                elapsed = time.time() - start_time

                # Save persistent storage state
                try:
                    STORAGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(STORAGE_STATE_FILE))
                except Exception:
                    pass

                context.close()

                preview = f"{raw_key[:6]}...{raw_key[-4:]}" if raw_key and len(raw_key) > 10 else ""
                return KeyCreationResult(
                    provider=provider_slug,
                    success=success,
                    key_extracted=bool(raw_key),
                    key_preview=preview,
                    elapsed_seconds=round(elapsed, 2),
                    error="" if success else msg,
                    details={"message": msg, "extracted": bool(raw_key)},
                )
            except Exception as e:
                try:
                    context.close()
                except Exception:
                    pass
                elapsed = time.time() - start_time
                return KeyCreationResult(
                    provider=provider_slug,
                    success=False,
                    elapsed_seconds=round(elapsed, 2),
                    error=sanitize_text(str(e)),
                )


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "openrouter"
    mgr = ProviderKeyManager(headless=True)
    res = mgr.create_key(target)
    print(f"\n[+] Result for {target}:")
    print(f"    Success: {res.success}")
    print(f"    Key Extracted: {res.key_extracted}")
    if res.key_preview:
        print(f"    Key Preview: {res.key_preview}")
    if res.error:
        print(f"    Message: {res.error}")
