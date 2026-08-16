import asyncio
import datetime
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import async_playwright, Page, BrowserContext  # noqa: E402
from omniroute_api import OmniRouteAPI, log, mask_token, save_json  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STORAGE_STATE_PATH = os.path.join(PROJECT_ROOT, "state", "browser_profile", "storage_state.json")
KEYS_FILE = os.path.join(PROJECT_ROOT, "state", "generated_keys.json")

class ProviderKeyAdapter:
    def __init__(self, context: BrowserContext, page: Page):
        self.context = context
        self.page = page
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.key_name = f"omniroute-auto-{self.timestamp}"

    async def _wait_for_login(self, target_url: str, login_indicator: str):
        log(f"Checking session state for {target_url}...")
        await self.page.goto(target_url, wait_until="domcontentloaded")
        content = await self.page.content()
        if login_indicator in content.lower():
            log(f"[!] Authentication Wall Detected on {target_url}.", "warn")
            return False
        return True


class GitHubAdapter(ProviderKeyAdapter):
    async def generate_key(self) -> str:
        target_url = "https://github.com/settings/tokens/new"
        await self.page.goto(target_url, wait_until="domcontentloaded")
        content = await self.page.content()
        if "sign in" in content.lower():
            log("[!] GitHub Authentication Wall Detected.", "warn")
            return None

        log("Executing GitHub 'Create New Token (classic)' flow...")
        try:
            desc_input = self.page.locator('input#oauth_access_description, input[name="oauth_access[description]"]').first
            await desc_input.fill(self.key_name)
            # Submit form
            submit_btn = self.page.locator('button:has-text("Generate token")').first
            await submit_btn.click()
            await self.page.wait_for_timeout(3000)
            
            token_el = self.page.locator("code#new-oauth-token, code.user-select-contain").first
            token = await token_el.inner_text()
            return token.strip() if token else None
        except Exception as e:
            log(f"GitHub Adapter Error: {e}", "err")
            return None


class AnthropicAdapter(ProviderKeyAdapter):
    async def generate_key(self) -> str:
        target_url = "https://platform.claude.com/settings/keys"
        if not await self._wait_for_login(target_url, "sign in"):
            return None

        log("Executing Anthropic 'Create Key' flow on platform.claude.com...")
        try:
            await self.page.wait_for_timeout(3000)
            create_btn = self.page.get_by_role("button", name=re.compile("Create key", re.I)).first
            await create_btn.click(timeout=8000)
            await self.page.wait_for_timeout(2000)
            
            dlg = self.page.locator('[role="dialog"]').first
            name_input = dlg.locator('input[placeholder="my-secret-key"], input[name="name"]').first
            await name_input.fill(self.key_name)
            await self.page.wait_for_timeout(800)
            
            add_btn = dlg.locator('button[type="submit"], button:has-text("Add")').first
            if await add_btn.is_disabled():
                exp_btn = dlg.locator('[role="combobox"]:has-text("Select an expiration")').first
                await exp_btn.click(timeout=5000)
                await self.page.wait_for_timeout(1000)
                for opt_name in ("No expiration", "Never", "30 days", "90 days", "1 year"):
                    try:
                        opt = self.page.get_by_role("option", name=re.compile(opt_name, re.I)).first
                        await opt.click(timeout=2000)
                        break
                    except Exception:
                        continue
                await self.page.wait_for_timeout(800)
                
            await add_btn.click(timeout=5000)
            await self.page.wait_for_timeout(3000)
            
            # Extract plaintext key
            key_el = self.page.locator("input[value^='sk-ant'], code:has-text('sk-ant'), pre:has-text('sk-ant')").first
            val = await key_el.get_attribute("value") or await key_el.inner_text()
            return val.strip() if val else None
        except Exception as e:
            log(f"Anthropic Adapter Error: {e}", "err")
            return None


class OpenRouterAdapter(ProviderKeyAdapter):
    async def generate_key(self) -> str:
        target_url = "https://openrouter.ai/settings/keys"
        if not await self._wait_for_login(target_url, "sign in"):
            return None

        log("Executing OpenRouter 'Create Key' flow...")
        try:
            await self.page.wait_for_timeout(3000)
            create_btn = self.page.locator("button:has-text('Create Key'), button:has-text('New Key')").first
            await create_btn.click(timeout=8000)
            await self.page.wait_for_timeout(2000)
            
            name_input = self.page.locator("input#name, input[placeholder*='key name' i]").first
            await name_input.fill(self.key_name)
            await self.page.wait_for_timeout(500)
            
            submit_btn = self.page.locator("button[type='submit']:has-text('Create'), button:has-text('Create')").first
            await submit_btn.click(timeout=5000)
            await self.page.wait_for_timeout(3000)
            
            # Modal reveal
            key_el = self.page.locator("input[value^='sk-or'], code:has-text('sk-or')").first
            val = await key_el.get_attribute("value") or await key_el.inner_text()
            return val.strip() if val else None
        except Exception as e:
            log(f"OpenRouter Adapter Error: {e}", "err")
            return None
