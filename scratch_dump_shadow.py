import asyncio
from playwright.async_api import async_playwright
import json
import subprocess
import time

async def main():
    port = 9223
    print("Launching Chrome...")
    cmd = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir=D:\\omniroute-monetizer\\state\\automation_profiles\\niloy",
        f"--profile-directory=Profile 17",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    proc = subprocess.Popen(cmd)
    time.sleep(5)
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            page = context.pages[0]
            await page.goto("https://labs.google/fx/tools/flow")
            await page.wait_for_timeout(5000)
            
            # Find all textareas and inputs, even in shadow DOMs
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
                
                const allRoots = [document].concat(getShadows(document));
                let results = [];
                for (const root of allRoots) {
                    const textareas = root.querySelectorAll('textarea, [contenteditable="true"], button');
                    textareas.forEach(t => {
                        let obj = {
                            tag: t.tagName,
                            placeholder: t.getAttribute('placeholder'),
                            text: t.innerText || t.textContent,
                            ariaLabel: t.getAttribute('aria-label'),
                            role: t.getAttribute('role'),
                            id: t.id,
                            className: t.className
                        };
                        results.push(obj);
                    });
                }
                return results;
            }
            """
            elements = await page.evaluate(js)
            with open("D:\\omniroute-monetizer\\flow_elements.json", "w") as f:
                json.dump(elements, f, indent=2)
            print(f"Dumped {len(elements)} elements")
            
            await browser.close()
    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
