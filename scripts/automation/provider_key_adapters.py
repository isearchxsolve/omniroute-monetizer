import asyncio
import datetime
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import async_playwright, Page, BrowserContext  # noqa: E402

from omniroute_api import OmniRouteAPI, log, mask_token, save_json  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STORAGE_STATE_PATH = os.path.join(PROJECT_ROOT, "state", "browser_profile", "storage_state.json")

class ProviderKeyAdapter:
    def __init__(self, context: BrowserContext, page: Page):
        self.context = context
        self.page = page
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.key_name = f"omniroute-auto-{self.timestamp}"

    async def _wait_for_login(self, target_url: str, login_indicator: str):
        print(f"Checking session state for {target_url}...")
        await self.page.goto(target_url, wait_until="domcontentloaded")
        
        content = await self.page.content()
        if login_indicator in content.lower():
            print(f"[!] Authentication Wall Detected on {target_url}.")
            print("Session missing or expired. Cannot proceed without manual login.")
            return False
        return True

class GitHubAdapter(ProviderKeyAdapter):
    async def generate_key(self) -> str:
        target_url = "https://github.com/settings/tokens/new"
        
        # Note: GitHub tokens often require sudo mode (password re-entry) even with active sessions.
        # This is a simplified adapter assuming session is valid and sudo mode is not active.
        await self.page.goto(target_url, wait_until="domcontentloaded")
        
        content = await self.page.content()
        if "sign in" in content.lower():
            print("[!] GitHub Authentication Wall Detected.")
            return None
            
        print("Executing GitHub 'Create New Token' flow...")
        try:
            # Fill Note
            await self.page.fill("input#oauth_access_description", self.key_name)
            
            # Check 'repo' scope as an example
            await self.page.check("input#repo")
            
            # Click Generate token
            await self.page.click("button:has-text('Generate token')")
            
            # Extract Token
            await self.page.wait_for_selector("code#new-oauth-token")
            token_el = await self.page.query_selector("code#new-oauth-token")
            token = await token_el.inner_text()
            return token.strip()
        except Exception as e:
            print(f"GitHub Adapter Error: {e}")
            return None

class AnthropicAdapter(ProviderKeyAdapter):
    async def generate_key(self) -> str:
        target_url = "https://console.anthropic.com/settings/keys"
        
        if not await self._wait_for_login(target_url, "sign in"):
            return None
            
        print("Executing Anthropic 'Create New Key' flow...")
        try:
            await self.page.click("button:has-text('Create Key')")
            await self.page.fill("input[name='name']", self.key_name)
            await self.page.click("button:has-text('Create')")
            
            # Wait for modal and extract key
            # Assuming key is presented in an input or pre element
            await self.page.wait_for_selector("input[value^='sk-ant']")
            key_el = await self.page.query_selector("input[value^='sk-ant']")
            token = await key_el.get_attribute("value")
            
            # Close modal
            await self.page.click("button:has-text('Done')")
            return token.strip()
        except Exception as e:
            print(f"Anthropic Adapter Error: {e}")
            return None

class OpenRouterAdapter(ProviderKeyAdapter):
    async def generate_key(self) -> str:
        target_url = "https://openrouter.ai/keys"
        
        if not await self._wait_for_login(target_url, "sign in"):
            return None
            
        print("Executing OpenRouter 'Create New Key' flow...")
        try:
            await self.page.click("button:has-text('Create Key')")
            await self.page.fill("input[placeholder='Key Name']", self.key_name)
            await self.page.click("button:has-text('Create')")
            
            # Extract key
            await self.page.wait_for_selector("input[value^='sk-or-']")
            key_el = await self.page.query_selector("input[value^='sk-or-']")
            token = await key_el.get_attribute("value")
            return token.strip()
        except Exception as e:
            print(f"OpenRouter Adapter Error: {e}")
            return None

def inject_key_into_omniroute(provider: str, key: str) -> dict:
    """Hot-inject a freshly generated key into the matching OmniRoute connection.

    Only targets authType == 'apikey' connections. Verifies with the
    connection test endpoint. Never logs the raw key.
    """
    result = {"provider": provider, "key": mask_token(key), "injected": False, "test_valid": None}
    api = OmniRouteAPI()
    if not api.login():
        result["note"] = "management login unavailable"
        return result
    connections = api.get_connections()
    candidates = [c for c in connections
                  if c.get("provider") == provider and c.get("authType") == "apikey"]
    if not candidates:
        result["note"] = "no apikey connection for provider; nothing to inject into"
        log(f"{provider}: {result['note']}", "skip")
        return result
    conn = candidates[0]
    cid = conn.get("id")
    res = api.update_connection(cid, {"apiKey": key})
    result["connection_id"] = cid
    result["http_status"] = res.get("http_status")
    if res.get("http_status") == 200:
        result["injected"] = True
        test = api.test_connection(cid)
        result["test_valid"] = bool((test.get("result") or {}).get("valid"))
        log(f"{provider}: key injected, test valid={result['test_valid']}",
            "ok" if result["test_valid"] else "warn")
    else:
        result["note"] = f"injection failed HTTP {res.get('http_status')}"
        log(f"{provider}: {result['note']}", "err")
    return result


async def main(provider: str, inject: bool = True):
    user_data_dir = os.path.join(PROJECT_ROOT, "state", "browser_profile")
    os.makedirs(user_data_dir, exist_ok=True)

    print(f"Initializing Tier 2 Playwright Engine for {provider}...")

    async with async_playwright() as p:
        # Resolution 2: persistent context keeps cookies/localStorage across runs
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
        )

        page = context.pages[0] if context.pages else await context.new_page()
        
        adapter = None
        if provider == "github":
            adapter = GitHubAdapter(context, page)
        elif provider == "anthropic":
            adapter = AnthropicAdapter(context, page)
        elif provider == "openrouter":
            adapter = OpenRouterAdapter(context, page)
        else:
            print(f"Unknown provider: {provider}")
            await context.close()
            return

        if adapter:
            key = await adapter.generate_key()
            if key:
                print(f"Successfully generated new key: {key[:6]}...{key[-4:]}")
                # Resolution 2: export session snapshot for reuse across cycles
                try:
                    await context.storage_state(path=STORAGE_STATE_PATH)
                    print(f"Session state exported: {os.path.basename(STORAGE_STATE_PATH)}")
                except Exception as e:
                    print(f"storage_state export failed: {e}")
                # Resolution 1: auto-inject into OmniRoute (PUT /api/providers/{id})
                if inject:
                    outcome = inject_key_into_omniroute(provider, key)
                    save_json("keygen_result.json", {
                        "provider": provider,
                        "generated": True,
                        "key": mask_token(key),
                        "outcome": outcome,
                    })
                else:
                    print("Injection skipped (--no-inject).")
            else:
                print("Key generation failed or aborted due to authentication wall.")
                save_json("keygen_result.json", {
                    "provider": provider,
                    "generated": False,
                    "note": "auth wall or generation failure; no credentials fabricated",
                })

        await context.close()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Tier 2 provider key generation adapters")
    ap.add_argument("provider", nargs="?", help="github|anthropic|openrouter")
    ap.add_argument("--no-inject", action="store_true", help="generate only, skip OmniRoute injection")
    args = ap.parse_args()
    if args.provider:
        asyncio.run(main(args.provider.lower(), inject=not args.no_inject))
    else:
        print("Usage: python provider_key_adapters.py [github|anthropic|openrouter] [--no-inject]")
