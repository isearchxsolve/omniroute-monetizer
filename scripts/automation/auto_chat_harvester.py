"""auto_chat_harvester.py — fully automated session harvesting & sentinel injection for web chat providers.

Connects to a running Chrome session (where user is already signed in, or guest mode),
navigates/attaches to the chat tab, automatically finds the prompt input (standard or Shadow DOM),
types the sentinel prompt, submits it, intercepts the full genuine HTTP request & response,
saves state/secrets/session_<host>.json, and validates it with universal_replay.py.

Usage:
    python auto_chat_harvester.py --port 9222 --url https://duckduckgo.com/ai --name duckduckgo_ai
    python auto_chat_harvester.py --port 9222 --all-tabs
    python auto_chat_harvester.py --port 9222 --target-list state/free_llm_chat_sites.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

SECRETS_DIR = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
SENTINEL_PROMPT = "Reply exactly one word: Omni."


def sanitize_host(url: str, override_name: str | None = None) -> str:
    if override_name:
        return override_name.replace("-", "_").replace(".", "_")
    hostname = urlsplit(url).hostname or "unknown"
    return hostname.replace("www.", "").replace("-", "_").replace(".", "_")


JS_FIND_AND_TYPE_PROMPT = """
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
    let inputEl = null;
    let submitBtn = null;

    for (const root of roots) {
        if (!inputEl) {
            // Textarea or contenteditable or input
            const tas = root.querySelectorAll('textarea, [contenteditable="true"], input[type="text"]');
            for (const el of tas) {
                // Ignore hidden elements
                const rect = el.getBoundingClientRect();
                if (rect.width > 30 && rect.height > 15) {
                    inputEl = el;
                    break;
                }
            }
        }
        if (!submitBtn) {
            const btns = root.querySelectorAll('button, [role="button"], input[type="submit"]');
            for (const b of btns) {
                const label = (b.getAttribute('aria-label') || '').toLowerCase();
                const text = (b.innerText || b.textContent || '').toLowerCase();
                const rect = b.getBoundingClientRect();
                if (rect.width > 10 && rect.height > 10) {
                    if (label.includes('send') || label.includes('submit') || label.includes('generate') ||
                        text.includes('send') || text.includes('submit') || text.includes('generate') ||
                        b.classList.contains('send') || b.querySelector('svg')) {
                        submitBtn = b;
                    }
                }
            }
        }
    }

    if (!inputEl) {
        return { success: false, error: "Input element not found in DOM or Shadow DOM" };
    }

    // Set value and dispatch events
    if (inputEl.tagName.toLowerCase() === 'textarea' || inputEl.tagName.toLowerCase() === 'input') {
        inputEl.focus();
        inputEl.value = promptText;
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        inputEl.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
        inputEl.focus();
        inputEl.innerText = promptText;
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // Try clicking submit button if found
    if (submitBtn) {
        submitBtn.click();
    } else {
        // Fallback: Dispatch Enter key
        inputEl.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        inputEl.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        inputEl.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
    }

    return { success: true };
}
"""


async def harvest_single_tab(page, name_override: str | None = None, timeout_secs: int = 30) -> dict | None:
    current_url = page.url
    host_key = sanitize_host(current_url, name_override)
    print(f"[*] [Harvesting] Page: {page.title()} ({current_url}) -> Host Key: {host_key}")

    captured_exchange = None
    capture_event = asyncio.Event()

    async def on_request(request):
        nonlocal captured_exchange
        if request.method in ["POST", "PUT"]:
            try:
                body = request.post_data or ""
                # Check if sentinel is in body or if this is the primary chat POST endpoint
                if (SENTINEL_PROMPT in body or "Omni" in body or "prompt" in body or "messages" in body) and not captured_exchange:
                    headers = request.headers
                    cookies = await page.context.cookies()
                    cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    
                    captured_exchange = {
                        "url": request.url,
                        "method": request.method,
                        "request_headers": {k: v for k, v in headers.items() if not k.startswith(":")},
                        "cookie_header": cookie_header,
                        "request_body": body,
                        "host": urlsplit(request.url).hostname or host_key
                    }
                    print(f"[+] Intercepted genuine chat POST to {request.url}")
                    capture_event.set()
            except Exception as e:
                pass

    page.on("request", on_request)

    # Inject and submit sentinel prompt
    print(f"[*] Injecting sentinel prompt: '{SENTINEL_PROMPT}'...")
    res = await page.evaluate(JS_FIND_AND_TYPE_PROMPT, SENTINEL_PROMPT)
    if not res.get("success"):
        print(f"[-] Evaluation warning: {res.get('error')}. Retrying with keyboard typing fallback...")
        try:
            await page.keyboard.type(SENTINEL_PROMPT, delay=20)
            await page.keyboard.press("Enter")
        except Exception as e:
            print(f"[-] Keyboard fallback error: {e}")

    try:
        await asyncio.wait_for(capture_event.wait(), timeout=timeout_secs)
    except asyncio.TimeoutError:
        print(f"[-] Timeout waiting for network capture on {current_url}")
        return None

    if not captured_exchange:
        return None

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = SECRETS_DIR / f"session_{host_key}.json"

    payload = {
        "host": captured_exchange["host"],
        "modality": "chat",
        "updated_at": int(time.time()),
        "cookie_header": captured_exchange["cookie_header"],
        "recorded_exchange": captured_exchange,
        "status": {
            "alive": True,
            "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reason": "automated_harvest"
        }
    }

    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[+] Saved harvest to: {out_file}")

    # Immediately verify replay with universal_replay
    print(f"[*] Validating session via UniversalSessionClient...")
    try:
        from universal_replay import UniversalSessionClient
        client = UniversalSessionClient(payload)
        test_res = client.chat([{"role": "user", "content": "Reply exactly one word: Verified"}])
        print(f"[+] Replay verification SUCCESS: {test_res.get('text', '')[:120]}")
    except Exception as e:
        print(f"[!] Replay verification notice (non-fatal, session saved): {e}")

    return payload


async def run_harvester(port: int = 9222, url: str | None = None, name: str | None = None, all_tabs: bool = False):
    print(f"[*] Connecting to Chrome on CDP port {port}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as e:
            print(f"[-] Connection refused on port {port}. Please ensure Chrome is running with --remote-debugging-port={port}.")
            return

        contexts = browser.contexts
        if not contexts or not contexts[0].pages:
            print("[-] No browser tabs found.")
            return

        context = contexts[0]

        if all_tabs:
            print(f"[*] Harvesting across all {len(context.pages)} open tabs...")
            for idx, page in enumerate(context.pages):
                await page.bring_to_front()
                await asyncio.sleep(1)
                await harvest_single_tab(page)
        elif url:
            page = context.pages[0]
            print(f"[*] Navigating to {url}...")
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await harvest_single_tab(page, name_override=name)
        else:
            # Active front page
            page = context.pages[0]
            await harvest_single_tab(page, name_override=name)


def main():
    parser = argparse.ArgumentParser(description="Automated Chat Harvester")
    parser.add_argument("--port", type=int, default=9222, help="Chrome CDP port")
    parser.add_argument("--url", type=str, help="Target URL to navigate and harvest")
    parser.add_argument("--name", type=str, help="Custom provider name for saved session")
    parser.add_argument("--all-tabs", action="store_true", help="Harvest all open tabs in sequence")

    args = parser.parse_args()
    asyncio.run(run_harvester(port=args.port, url=args.url, name=args.name, all_tabs=args.all_tabs))


if __name__ == "__main__":
    main()
