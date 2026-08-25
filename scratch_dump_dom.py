import asyncio
from playwright.async_api import async_playwright
import time
import subprocess

async def dump_flow():
    port = 9223
    print(f"[{port}] Launching Chrome...")
    cmd = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir=D:\\omniroute-monetizer\\state\\automation_profiles\\niloy",
        f"--profile-directory=Profile 17",
        "--no-first-run",
        "--no-default-browser-check",
        "https://labs.google/fx/tools/flow"
    ]
    proc = subprocess.Popen(cmd)
    time.sleep(8)
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        target_page = None
        for page in browser.contexts[0].pages:
            if "labs.google" in page.url:
                target_page = page
                break
        if not target_page:
            target_page = browser.contexts[0].pages[0]
            await target_page.goto("https://labs.google/fx/tools/flow")
            await target_page.wait_for_load_state("networkidle")
            
        print("Taking screenshot...")
        await target_page.screenshot(path="D:\\omniroute-monetizer\\flow_screenshot.png")
        
        print("Dumping HTML...")
        with open("D:\\omniroute-monetizer\\flow_dom.html", "w", encoding="utf-8") as f:
            f.write(await target_page.content())
            
        await browser.close()
    
    proc.terminate()
    print("Done")

if __name__ == "__main__":
    asyncio.run(dump_flow())
