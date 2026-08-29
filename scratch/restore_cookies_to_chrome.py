import asyncio
import json
import os
import pathlib
from urllib.parse import urlparse

from playwright.async_api import async_playwright

SECRETS_DIR = pathlib.Path("state/secrets")

async def main():
    if not SECRETS_DIR.exists():
        print("No secrets directory found.")
        return

    print("[*] Connecting to CDP at http://localhost:9222...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"[-] Failed to connect: {e}")
            return

        contexts = browser.contexts
        if not contexts:
            print("[-] No browser context found.")
            return

        context = contexts[0]
        
        # 1. Gather all cookies from session files
        restored_hosts = set()
        for sf in SECRETS_DIR.glob("session_*.json"):
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                host = data.get("host")
                cookie_header = data.get("cookie_header")
                
                if not host or not cookie_header:
                    continue
                
                # Parse cookie header
                # e.g., "cookie1=value1; cookie2=value2"
                cookies = []
                for pair in cookie_header.split(";"):
                    pair = pair.strip()
                    if not pair: continue
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        cookies.append({
                            "name": k.strip(),
                            "value": v.strip(),
                            "domain": host if host.startswith(".") else "." + host,
                            "path": "/"
                        })
                
                if cookies:
                    await context.add_cookies(cookies)
                    restored_hosts.add(host)
                    print(f"[+] Injected {len(cookies)} cookies for {host}")
            except Exception as e:
                print(f"[-] Error processing {sf.name}: {e}")

        # 2. Reload pages matching the restored hosts
        print("\n[*] Reloading tabs to apply restored sessions...")
        for page in context.pages:
            try:
                url = page.url
                domain = urlparse(url).netloc
                # Simple loose match
                if any(rh in domain or domain in rh for rh in restored_hosts):
                    print(f"    -> Reloading {url}")
                    await page.reload()
            except Exception as e:
                pass
                
        print("\n[+] Cookie restore complete!")

if __name__ == "__main__":
    asyncio.run(main())
