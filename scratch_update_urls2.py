import asyncio
from playwright.async_api import async_playwright
import json

SEATS = {
    "niloy-1": 9223,
    "flow-seat2": 9224,
    "flow-seat3": 9225
}

async def fix_seat(p, label, port):
    print(f"[{label}] Connecting to port {port}...")
    try:
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        context = browser.contexts[0]
        
        page = None
        for p_tab in context.pages:
            if "labs.google" in p_tab.url:
                page = p_tab
                break
        if not page:
            page = context.pages[0]
            
        await page.goto("https://labs.google/fx/tools/flow", wait_until="load")
        await page.wait_for_timeout(3000)
        
        js = """
        () => {
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
            for (const root of roots) {
                const links = root.querySelectorAll('a');
                for (const a of links) {
                    if ((a.href || '').includes('/project/')) {
                        a.click();
                        return true;
                    }
                }
                const btns = root.querySelectorAll('button');
                for (const b of btns) {
                    let btext = (b.innerText || b.textContent || '').trim().toLowerCase();
                    if (btext.includes("new project") || btext.includes("add_2")) {
                        b.click();
                        return true;
                    }
                }
            }
            return false;
        }
        """
        clicked = await page.evaluate(js)
        if clicked:
            print(f"[{label}] Clicked project link. Waiting for URL to change...")
            await page.wait_for_timeout(5000)
        else:
            print(f"[{label}] Could not find any project link to click!")
        
        url = page.url
        await browser.close()
        
        if "/project/" in url:
            print(f"[{label}] SUCCESS! URL: {url}")
            return url
        else:
            print(f"[{label}] FAILED. Current URL: {url}")
            return None
    except Exception as e:
        print(f"[{label}] Error: {e}")
        return None

async def main():
    with open(r"D:\omniroute-monetizer\state\video_accounts.json", "r") as f:
        data = json.load(f)
        
    async with async_playwright() as p:
        for acct in data["accounts"]:
            label = acct["label"]
            if label in SEATS:
                port = SEATS[label]
                url = await fix_seat(p, label, port)
                if url:
                    acct["url"] = url
                    
    with open(r"D:\omniroute-monetizer\state\video_accounts.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Updated video_accounts.json!")

if __name__ == "__main__":
    asyncio.run(main())
