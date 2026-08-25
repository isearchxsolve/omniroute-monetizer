import asyncio
from playwright.async_api import async_playwright
import time
import subprocess
import json
import os

SEATS = {
    "niloy": 9223,
    "flow-seat2": 9224,
    "flow-seat3": 9225
}

async def init_seat(profile_name, port):
    print(f"[{profile_name}] Launching Chrome on port {port}...")
    cmd = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir=D:\\omniroute-monetizer\\state\\automation_profiles\\{profile_name}",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    proc = subprocess.Popen(cmd)
    await asyncio.sleep(5)
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            
            page = None
            for p_tab in context.pages:
                if "labs.google" in p_tab.url:
                    page = p_tab
                    break
            if not page:
                page = context.pages[0]
            
            await page.goto("https://labs.google/fx/tools/flow", wait_until="networkidle")
            await page.wait_for_timeout(5000)
            
            async def click_button_by_text(texts):
                js = f"""
                () => {{
                    const texts = {json.dumps(texts)};
                    const getShadows = (root) => {{
                        let shadows = [];
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                        let node;
                        while (node = walker.nextNode()) {{
                            if (node.shadowRoot) {{
                                shadows.push(node.shadowRoot);
                                shadows = shadows.concat(getShadows(node.shadowRoot));
                            }}
                        }}
                        return shadows;
                    }};
                    const roots = [document].concat(getShadows(document));
                    for (const root of roots) {{
                        const btns = root.querySelectorAll('button');
                        for (const b of btns) {{
                            let btext = (b.innerText || b.textContent || '').trim().toLowerCase();
                            for (let t of texts) {{
                                if (btext === t.toLowerCase()) {{
                                    b.click();
                                    return t;
                                }}
                            }}
                        }}
                    }}
                    return null;
                }}
                """
                return await page.evaluate(js)

            # Onboarding loop to clear ToS and popups
            onboarding_buttons = ["Next", "Continue", "Get started", "I agree", "Got it", "Agree"]
            for i in range(10):
                if "/project/" in page.url:
                    break
                clicked = await click_button_by_text(onboarding_buttons)
                if clicked:
                    print(f"[{profile_name}] Clicked onboarding button: '{clicked}'")
                    await page.wait_for_timeout(3000)
                else:
                    break
            
            # If not in a project, click New project
            if "/project/" not in page.url:
                print(f"[{profile_name}] URL is {page.url}, looking for 'New project'...")
                clicked_new = await click_button_by_text(["New project", "add_2\nNew project"])
                if clicked_new:
                    print(f"[{profile_name}] Clicked 'New project'. Waiting for navigation...")
                    await page.wait_for_timeout(5000)
                else:
                    print(f"[{profile_name}] Could not find 'New project' button.")
            
            if "/project/" in page.url:
                print(f"[{profile_name}] SUCCESS! Seat is initialized and ready in a project: {page.url}")
            else:
                print(f"[{profile_name}] FAILED to reach a project URL. Current URL: {page.url}")
                
            await browser.close()
    except Exception as e:
        print(f"[{profile_name}] Error: {e}")
    finally:
        print(f"[{profile_name}] Closing Chrome...")
        proc.terminate()
        await asyncio.sleep(3)

async def main():
    for profile, port in SEATS.items():
        await init_seat(profile, port)
    print("All seats processed sequentially!")

if __name__ == "__main__":
    asyncio.run(main())
