import asyncio
import json
import os
import sys
import time
from playwright.async_api import async_playwright

STATE_FILE = r"D:\omniroute-monetizer\state\video_accounts.json"

async def generate_video(prompt, target_provider="flow"):
    # 1. Load accounts
    if not os.path.exists(STATE_FILE):
        print(f"[-] Error: {STATE_FILE} not found.")
        return False
        
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # 2. Find a healthy account for this provider
    account = None
    for acct in data.get("accounts", []):
        if acct.get("provider") == target_provider and acct.get("health") == "green":
            account = acct
            break
            
    if not account:
        print(f"[-] Error: No healthy '{target_provider}' accounts available.")
        return False
        
    port = account["port"]
    url = account.get("url")
    label = account["label"]
    
    if not url:
        print(f"[-] Error: Account {label} has no project URL saved.")
        return False
        
    print(f"[+] Routing to {label} (Port: {port})")
    
    async with async_playwright() as p:
        try:
            print(f"[+] Connecting to CDP on port {port}...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            
            # Find or open the target URL
            page = None
            for p_tab in context.pages:
                if target_provider == "flow" and "labs.google/fx/tools/flow" in p_tab.url:
                    page = p_tab
                    break
            
            if not page:
                page = context.pages[0]
                
            print(f"[+] Navigating to {url}")
            await page.goto(url, wait_until="load")
            await page.wait_for_timeout(3000)
            
            if target_provider == "flow":
                # Use Shadow DOM traversal to find the textarea and submit button
                js_inject = """
                (promptText) => {
                    const getShadows = (root) => {
                        let shadows = [];
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                        let node;
                        while (node = walker.nextNode()) {
                            if (node.shadowRoot) {
                                shadows.push(node.shadowRoot);
                                shadows = shadows.concat(getShadows(node.shadowRoot));
                            }
                        }
                        return shadows;
                    };
                    
                    const roots = [document].concat(getShadows(document));
                    let textarea = null;
                    let submitBtn = null;
                    
                    for (const root of roots) {
                        if (!textarea) {
                            const tas = root.querySelectorAll('textarea');
                            for (const ta of tas) {
                                textarea = ta;
                                break;
                            }
                        }
                        if (!submitBtn) {
                            const btns = root.querySelectorAll('button');
                            for (const b of btns) {
                                let label = (b.getAttribute('aria-label') || '').toLowerCase();
                                let text = (b.innerText || b.textContent || '').toLowerCase();
                                if (label.includes('generate') || label.includes('create') || text.includes('generate')) {
                                    submitBtn = b;
                                    break;
                                }
                            }
                        }
                    }
                    
                    if (textarea && submitBtn) {
                        textarea.value = promptText;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                        
                        setTimeout(() => {
                            submitBtn.click();
                        }, 500);
                        return "SUCCESS";
                    }
                    
                    return `Missing elements. Textarea: ${!!textarea}, Button: ${!!submitBtn}`;
                }
                """
                
                print(f"[+] Injecting prompt: '{prompt}'")
                result = await page.evaluate(js_inject, prompt)
                print(f"[+] Injection Result: {result}")
                
                if result == "SUCCESS":
                    print("[+] Video generation triggered successfully!")
                
            await page.wait_for_timeout(2000)
            await browser.close()
            return True
            
        except Exception as e:
            print(f"[-] Playwright Error: {e}")
            return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python video_universal_replay.py <provider: flow|veo> <prompt>")
        sys.exit(1)
        
    provider = sys.argv[1].lower()
    prompt = sys.argv[2]
    
    asyncio.run(generate_video(prompt, provider))
