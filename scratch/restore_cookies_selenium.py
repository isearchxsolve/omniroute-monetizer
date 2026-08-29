import json
import os
import pathlib
from urllib.parse import urlparse
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

SECRETS_DIR = pathlib.Path("state/secrets")

def main():
    if not SECRETS_DIR.exists():
        print("No secrets directory found.")
        return

    print("[*] Loading cookies from session files...")
    # Load all cookies into a map of domain -> cookies
    domain_cookies = {}
    for sf in SECRETS_DIR.glob("session_*.json"):
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            host = data.get("host")
            cookie_header = data.get("cookie_header")
            if not host or not cookie_header:
                continue
            
            cookies = []
            for pair in cookie_header.split(";"):
                pair = pair.strip()
                if not pair: continue
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    cookies.append({
                        "name": k.strip(),
                        "value": v.strip(),
                        "domain": host if host.startswith(".") else "." + host
                    })
            
            if cookies:
                domain_cookies[host] = cookies
        except Exception as e:
            print(f"[-] Error parsing {sf.name}: {e}")

    print(f"[*] Found cookies for {len(domain_cookies)} domains.")

    print("[*] Connecting to Chrome on port 9222 via Selenium...")
    opts = Options()
    opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    try:
        driver = webdriver.Chrome(options=opts)
    except Exception as e:
        print(f"[-] Failed to connect to Chrome: {e}")
        return

    print("[*] Iterating through open tabs...")
    restored_count = 0
    try:
        handles = driver.window_handles
        for handle in handles:
            try:
                driver.switch_to.window(handle)
                url = driver.current_url
                if not url or url.startswith("chrome://"):
                    continue
                
                domain = urlparse(url).netloc
                # Find matching cookies
                matched_host = None
                for host in domain_cookies.keys():
                    if host in domain or domain in host:
                        matched_host = host
                        break
                
                if matched_host:
                    print(f"  -> Restoring cookies for {matched_host} on tab {url[:50]}...")
                    cookies_to_add = domain_cookies[matched_host]
                    added = 0
                    for c in cookies_to_add:
                        try:
                            # Add cookie requires domain to match exactly or loosely
                            driver.add_cookie(c)
                            added += 1
                        except WebDriverException as e:
                            # Sometimes strict domain restrictions fail the add_cookie call
                            # Try without explicit domain (defaults to current domain)
                            try:
                                c_fallback = {"name": c["name"], "value": c["value"]}
                                driver.add_cookie(c_fallback)
                                added += 1
                            except Exception:
                                pass
                    
                    if added > 0:
                        print(f"     [+] Added {added} cookies. Reloading tab.")
                        driver.refresh()
                        restored_count += 1
                        # Remove from dict so we don't restore multiple times for same host?
                        # Or keep it in case there are multiple tabs.
            except Exception as e:
                print(f"  [-] Error on a tab: {e}")
    finally:
        # DO NOT quit driver, it will close the operator's browser!
        pass

    print(f"\n[+] Successfully restored cookies for {restored_count} tabs!")

if __name__ == "__main__":
    main()
