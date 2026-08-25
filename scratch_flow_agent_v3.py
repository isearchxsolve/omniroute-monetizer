import asyncio
from playwright.async_api import async_playwright
import time
import subprocess
import os
import json

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

            # Onboarding loop
            onboarding_buttons = ["Next", "Continue", "Get started", "I agree", "Got it", "Agree", "New project"]
            for i in range(10):
                clicked = await click_button_by_text(onboarding_buttons)
                if clicked:
                    print(f"[{profile_name}] Clicked onboarding button: '{clicked}'")
                    await page.wait_for_timeout(3000)
                else:
                    break
            
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
                            const txt = (b.innerText || '').toLowerCase().trim();
                            if (txt === 'create' || txt === 'generate') {
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
    print("Done processing niloy.")

if __name__ == "__main__":
    asyncio.run(main())
