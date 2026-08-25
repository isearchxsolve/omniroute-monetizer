import asyncio
import json
import os
import sys
import time
from playwright.async_api import async_playwright

async def sniff_session(url_to_open, site_name, port=9301):
    """
    Opens Chrome on the given port, navigates to the URL, and waits for a network request
    containing our sentinel string. Saves the intercepted request to state/secrets/session_{site_name}.json.
    """
    async with async_playwright() as p:
        try:
            print(f"[*] Launching/connecting to Chrome on port {port}...")
            # We connect to an existing Chrome instance or we could launch one.
            # Usually, you'd start Chrome with:
            # chrome.exe --remote-debugging-port=9301 --user-data-dir=D:\omniroute-monetizer\state\claude_profiles\seat1
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as e:
            print(f"[-] Failed to connect to CDP on port {port}: {e}")
            print(f"[-] Make sure you launched Chrome with --remote-debugging-port={port}")
            return
            
        contexts = browser.contexts
        if not contexts:
            return
            
        target_page = contexts[0].pages[0] if contexts[0].pages else await contexts[0].new_page()
        print(f"[*] Navigating to {url_to_open}...")
        await target_page.goto(url_to_open)
        
        captured_req = None
        
        async def on_request(request):
            nonlocal captured_req
            if request.method in ["POST", "PUT"]:
                try:
                    post_data = request.post_data
                    if post_data and ("Reply exactly one word: Omni." in post_data or "Reply exactly one word: Omni" in post_data):
                        print(f"[+] Intercepted sentinel POST request to: {request.url}")
                        
                        # We also need the cookies to reconstruct the Cookie header
                        cookies = await target_page.context.cookies()
                        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                        
                        captured_req = {
                            "method": request.method,
                            "url": request.url,
                            "request_headers": request.headers,
                            "cookie_header": cookie_header,
                            "request_body": post_data,
                            "host": site_name
                        }
                except Exception:
                    pass
                    
        target_page.on("request", on_request)
        
        print(f"[*] Ready! Please log in to {site_name} (if needed) and type this EXACT prompt into the chat:")
        print(f"    Reply exactly one word: Omni.")
        print(f"[*] Waiting for you to send the prompt...")
        
        # Wait until captured
        while not captured_req:
            await target_page.wait_for_timeout(1000)
            
        secrets_dir = os.path.join(r"D:\omniroute-monetizer\state\secrets")
        os.makedirs(secrets_dir, exist_ok=True)
        sess_file = os.path.join(secrets_dir, f"session_{site_name}.json")
        
        payload = {
            "host": site_name,
            "recorded_exchange": captured_req,
            "updated_at": int(time.time()),
            "cookie_header": captured_req["cookie_header"]
        }
        
        with open(sess_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            
        print(f"[+] SUCCESS! Sniffed session saved to {sess_file}")
        print(f"[*] You can now use this session with universal_replay.py")
        
        await browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python claude_session_sniff.py <url> <site_name> [port]")
        print("Example: python claude_session_sniff.py https://huggingface.co/chat huggingchat 9301")
        sys.exit(1)
        
    url = sys.argv[1]
    name = sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 9301
    
    asyncio.run(sniff_session(url, name, port))
