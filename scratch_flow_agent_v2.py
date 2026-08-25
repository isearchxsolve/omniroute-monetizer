import asyncio
from playwright.async_api import async_playwright
import time
import subprocess
import os

async def process_seat(profile_name):
    port = 9223
    print(f"[{profile_name}] Launching Chrome...")
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
    
    # Start sweep_grab in the background to listen to this port
    sweep_cmd = ["python", r"D:\omniroute-monetizer\scripts\automation\sweep_grab.py", "--port", str(port), "sweep", "--wait", "30"]
    sweep_proc = subprocess.Popen(sweep_cmd)
    
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
            
            await page.goto("https://labs.google/fx/tools/flow")
            await page.wait_for_timeout(5000)
            
            async def find_and_click(text):
                js = f"""
                () => {{
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
                            if ((b.innerText || '').includes('{text}') || (b.textContent || '').includes('{text}')) {{
                                b.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}
                """
                return await page.evaluate(js)

            clicked_next = await find_and_click("Next")
            if clicked_next:
                print(f"[{profile_name}] Clicked 'Next'.")
                await page.wait_for_timeout(2000)
                clicked_agree = await find_and_click("I agree") or await find_and_click("Agree") or await find_and_click("Got it")
                if clicked_agree:
                    print(f"[{profile_name}] Clicked 'Agree'.")
                await page.wait_for_timeout(3000)

            js_find_textarea = """
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
                    const textareas = root.querySelectorAll('textarea, [contenteditable="true"]');
                    for (const t of textareas) {
                        if (!t.id.includes("recaptcha") && (t.offsetWidth > 0 || t.offsetHeight > 0)) {
                            t.focus();
                            return true;
                        }
                    }
                }
                return false;
            }
            """
            found_textarea = await page.evaluate(js_find_textarea)
            if found_textarea:
                print(f"[{profile_name}] Found the prompt textarea! Typing...")
                await page.keyboard.type("A beautiful sunset over the ocean, cinematic, 4k, realistic")
                await page.wait_for_timeout(1000)
                
                js_click_generate = """
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
                        const btns = root.querySelectorAll('button');
                        for (const b of btns) {
                            const txt = (b.innerText || '').toLowerCase();
                            // avoid navigation links
                            if ((txt.includes('create') || txt.includes('generate')) && !txt.includes('help')) {
                                b.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
                """
                clicked_gen = await page.evaluate(js_click_generate)
                if clicked_gen:
                    print(f"[{profile_name}] Clicked the Create/Generate button! Wait for network grab.")
                else:
                    print(f"[{profile_name}] Could not find the Create button.")
            else:
                print(f"[{profile_name}] Could NOT find the prompt textarea.")
                
            # Wait for sweep grab to finish capturing
            sweep_proc.wait()
            
            await browser.close()
    except Exception as e:
        print(f"[{profile_name}] Error: {e}")
    finally:
        proc.terminate()
        try:
            sweep_proc.terminate()
        except:
            pass

async def main():
    await process_seat("niloy")
    print("Done processing niloy. Proceeding to flow-seat2 if successful.")

if __name__ == "__main__":
    asyncio.run(main())
