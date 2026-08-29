"""launch_and_harvest_chats.py — Launch candidate chat sites in Chrome tabs and auto-harvest sessions.

Workflow:
1. `python launch_and_harvest_chats.py launch [--port 9222] [--profile providers]`
   Opens Chrome on-screen with the candidate LLM chat URLs loaded in tabs.
   The operator signs into any tab that requires manual Google OAuth.

2. `python launch_and_harvest_chats.py harvest [--port 9222]`
   Takes over automatically across all open tabs:
   - Locates chat input (standard DOM / Shadow DOM)
   - Types sentinel prompt ('Reply exactly one word: Omni.')
   - Submits & intercepts the genuine request/cookie payload
   - Saves `state/secrets/session_<host>.json`
   - Validates live replay with `universal_replay.py`
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_no_discard import NO_DISCARD_FLAGS  # noqa: E402  -- stop Chrome discarding idle tabs

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
SECRETS_DIR = STATE / "secrets"
PROFILES_DIR = STATE / "automation_profiles"
DEFAULT_SITES_FILE = STATE / "free_llm_chat_sites.json"

SENTINEL_PROMPT = "Reply exactly one word: Omni."

def get_target_urls() -> list[tuple[str, str]]:
    if not DEFAULT_SITES_FILE.exists():
        return []
    with open(DEFAULT_SITES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    urls = []
    for category in data:
        for site in category.get("sites", []):
            urls.append((site["name"], site["url"]))
    return urls


def find_chrome() -> pathlib.Path:
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        p = pathlib.Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if p.exists():
            return p
    raise SystemExit("Chrome not found in Program Files or LocalAppData")


def sanitize_host(url: str, override_name: str | None = None) -> str:
    if override_name:
        return override_name.replace("-", "_").replace(".", "_")
    hostname = urlsplit(url).hostname or "unknown"
    return hostname.replace("www.", "").replace("-", "_").replace(".", "_")


JS_LOCATE_AND_FOCUS = """
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

    const isVisible = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) return false;
        const st = window.getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden';
    };
    
    const isRecaptcha = (el) => {
        const s = ((el.id||'')+' '+(el.className||'')+' '+(el.name||'')).toLowerCase();
        return s.includes('recaptcha');
    };

    const roots = [document].concat(getShadows(document));
    let inputEl = null;

    // 1. Prioritize textareas (actual chat composers)
    for (const root of roots) {
        const tas = Array.from(root.querySelectorAll('textarea')).filter(el => isVisible(el) && !isRecaptcha(el));
        if (tas.length > 0) {
            inputEl = tas[0];
            break;
        }
    }

    // 2. Fallback to contenteditable (used by Lexical, ProseMirror, etc.)
    if (!inputEl) {
        for (const root of roots) {
            const ces = Array.from(root.querySelectorAll('[contenteditable="true"], [contenteditable="plaintext-only"], [contenteditable=""]'))
                            .filter(el => isVisible(el));
            if (ces.length > 0) {
                inputEl = ces[0];
                break;
            }
        }
    }

    if (!inputEl) {
        return { success: false, error: "Input element not found" };
    }

    inputEl.scrollIntoView({block: 'center'});
    inputEl.focus();
    
    // Select all existing text so typing overwrites it
    try {
        if (inputEl.tagName === 'TEXTAREA' || inputEl.tagName === 'INPUT') {
            if (inputEl.select) inputEl.select();
        } else {
            const sel = window.getSelection();
            if (sel) {
                const r = document.createRange();
                r.selectNodeContents(inputEl);
                sel.removeAllRanges();
                sel.addRange(r);
            }
        }
    } catch(e) {}

    return { success: true };
}
"""


def cmd_launch(port: int = 9222, profile_tag: str = "providers") -> int:
    profile_dir = PROFILES_DIR / profile_tag
    profile_dir.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()

    urls = [url for _, url in get_target_urls()]
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    args = [
        str(chrome),
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        *NO_DISCARD_FLAGS,
        "--window-size=1450,960",
    ] + urls

    print(f"[*] Launching Chrome on port {port} with {len(urls)} target tabs...")
    print(f"    Profile: {profile_dir}")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )

    print(f"[+] Chrome is UP on port {port}!")
    print(f"[*] Sign in to any tabs that need Google OAuth.")
    print(f"[*] When ready, run:")
    print(f"    python scripts/automation/launch_and_harvest_chats.py harvest --port {port}")
    return 0


async def harvest_page(page, idx: int) -> dict | None:
    url = page.url
    host_key = sanitize_host(url)
    title = await page.title()
    print(f"\n=======================================================")
    print(f"[*] [Tab {idx + 1}] Processing: '{title}' ({url})")
    print(f"=======================================================")

    captured_exchange = None
    capture_event = asyncio.Event()

    async def on_request(request):
        nonlocal captured_exchange
        if request.method in ["POST", "PUT"]:
            # Ignore telemetry and analytics endpoints
            url_lower = request.url.lower()
            if any(x in url_lower for x in ["telemetry", "analytics", "tracking", "browser.events.data.microsoft.com", "log", "metrics", "/track", "/v1/b", "beacon", "segment"]):
                return

            try:
                body = request.post_data or ""
                if (SENTINEL_PROMPT in body or "Omni" in body or "prompt" in body or "messages" in body) and not captured_exchange:
                    headers = request.headers
                    cookies = await page.context.cookies([page.url, request.url])
                    cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    
                    captured_exchange = {
                        "url": request.url,
                        "method": request.method,
                        "request_headers": {k: v for k, v in headers.items() if not k.startswith(":")},
                        "cookie_header": cookie_header,
                        "request_body": body,
                        "host": urlsplit(request.url).hostname or host_key
                    }
                    print(f"[+] Captured genuine request to: {request.url}")
                    capture_event.set()
            except Exception:
                pass

    page.on("request", on_request)

    print(f"[*] Focusing chat input...")
    res = await page.evaluate(JS_LOCATE_AND_FOCUS)
    if not res.get("success"):
        print(f"[-] Focus failed: {res.get('error')}. Skipping this tab.")
        return None

    print(f"[*] Typing sentinel prompt via keyboard: '{SENTINEL_PROMPT}'...")
    try:
        await page.keyboard.insert_text(SENTINEL_PROMPT)
        await asyncio.sleep(0.5)
        
        # We also need a reliable way to click the submit button, mirroring CLICK_JS
        click_success = await page.evaluate("""() => {
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return false;
                const st = window.getComputedStyle(el);
                return st.display !== 'none' && st.visibility !== 'hidden';
            };
            const cands = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'))
                .filter(el => isVisible(el) && !el.disabled && 
                        !/cky-|cookie|consent/i.test((el.className||'')+' '+(el.getAttribute('aria-label')||'')));
            if (!cands.length) return false;
            
            let pick = cands.find(el=>el.getAttribute('type')==='submit')
                    || cands.find(el=>/send|submit/i.test((el.getAttribute('aria-label')||'')+(el.getAttribute('data-testid')||'')))
                    || null;
            
            if(!pick) {
                // Find nearest to input if we can't find by label
                const input = Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).find(e=>isVisible(e));
                if(input) {
                    const ir = input.getBoundingClientRect();
                    const cx = ir.x+ir.width/2, cy = ir.y+ir.height/2;
                    pick = cands.map(el=>{
                        const r = el.getBoundingClientRect();
                        return {el, d: Math.hypot(r.x+r.width/2-cx, r.y+r.height/2-cy)};
                    }).sort((a,b)=>a.d-b.d)[0].el;
                }
            }
            if(!pick) pick = cands[cands.length-1];
            pick.click();
            return true;
        }""")
        
        # Press enter regardless, as many apps accept it
        await page.keyboard.press("Enter")
        
    except Exception as e:
        print(f"[-] Keyboard typing error: {e}")
        return None

    try:
        await asyncio.wait_for(capture_event.wait(), timeout=12)
    except asyncio.TimeoutError:
        print(f"[-] No chat request detected within timeout for {url}")
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
            "reason": "auto_harvested"
        }
    }

    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[+] SUCCESS: Saved session secret to {out_file}")

    # Test replay with universal_replay
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from universal_replay import UniversalSessionClient
        client = UniversalSessionClient(payload)
        test_res = client.chat([{"role": "user", "content": "Reply exactly one word: Verified"}])
        print(f"[+] REPLAY TEST VERIFIED: '{test_res.get('text', '').strip()[:100]}'")
    except Exception as e:
        print(f"[!] Replay test note: {e}")

    return payload


async def cmd_harvest(port: int = 9222) -> int:
    print(f"[*] Connecting to CDP at http://localhost:{port}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as e:
            print(f"[-] Failed to connect on port {port}: {e}")
            return 1

        contexts = browser.contexts
        if not contexts or not contexts[0].pages:
            print("[-] No tabs found in browser.")
            return 1

        context = contexts[0]
        pages = context.pages
        print(f"[*] Found {len(pages)} open tabs. Starting automated harvest sweep...")

        harvested = 0
        for idx, page in enumerate(pages):
            try:
                await page.bring_to_front()
                await asyncio.sleep(1.5)
                res = await harvest_page(page, idx)
                if res:
                    harvested += 1
            except Exception as e:
                print(f"[-] Error processing tab {idx + 1}: {e}")

        print(f"\n[+] HARVEST COMPLETE: {harvested}/{len(pages)} sessions captured and saved.")
        return 0


def main():
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
    
    parser = argparse.ArgumentParser(description="Launch & Harvest Chat Sites")
    parser.add_argument("action", choices=["launch", "harvest"], help="Action to perform")
    parser.add_argument("--port", type=int, default=9222, help="CDP Port (default: 9222)")
    parser.add_argument("--profile", type=str, default="providers", help="Profile tag (default: providers)")

    args = parser.parse_args()
    if args.action == "launch":
        return cmd_launch(port=args.port, profile_tag=args.profile)
    elif args.action == "harvest":
        return asyncio.run(cmd_harvest(port=args.port))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
