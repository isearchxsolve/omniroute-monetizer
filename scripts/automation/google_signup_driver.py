"""
Google Sign-Up Driver for Fresh Chrome Profile
1. Navigates to target AI providers.
2. Locates and clicks "Sign In / Sign Up with Google".
3. Listens for Google OAuth chooser popup (accounts.google.com) and clicks the active Google account.
4. Confirms successful login redirect.
5. Captures session cookies & auth headers into state/secrets/session_<host>.json.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import websocket
import requests
import pathlib

PORT = 9222
OMNIROUTE_URL = "http://127.0.0.1:20128/v1/chat/completions"
OMNIROUTE_KEY = "sk-omniroute"
OMNIROUTE_MODEL = "frontier"
SECRETS_DIR = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
SECRETS_DIR.mkdir(parents=True, exist_ok=True)

def list_targets(port=PORT):
    url = f"http://127.0.0.1:{port}/json"
    req = urllib.request.urlopen(url, timeout=10)
    return json.loads(req.read().decode())

def get_tab(target_id=None, url_match=None):
    targets = list_targets()
    for t in targets:
        if t.get("type") != "page": continue
        if target_id and t.get("id") == target_id:
            return t
        if url_match and url_match in t.get("url", ""):
            return t
    return None

class CDPPage:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.msg_id = 0
        self.send("Page.bringToFront")
        self.send("Emulation.setFocusEmulationEnabled", {"enabled": True})

    def close(self):
        try: self.ws.close()
        except: pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, method, params=None):
        self.msg_id += 1
        payload = {"id": self.msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(payload))
        return self.msg_id

    def evaluate(self, expression, timeout=20):
        req_id = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(0.5)
            try:
                msg = json.loads(self.ws.recv())
                if msg.get("id") == req_id:
                    res = msg.get("result", {}).get("result", {})
                    if "value" in res:
                        return res["value"]
                    if msg.get("result", {}).get("exceptionDetails"):
                        err = msg["result"]["exceptionDetails"].get("exception", {}).get("description", "JS Error")
                        raise RuntimeError(f"JS Error: {err}")
                    return None
            except websocket.WebSocketTimeoutException:
                continue
        raise TimeoutError(f"evaluate timed out after {timeout}s")

    def get_cookies(self):
        req_id = self.send("Network.getCookies")
        deadline = time.time() + 10
        while time.time() < deadline:
            self.ws.settimeout(0.5)
            try:
                msg = json.loads(self.ws.recv())
                if msg.get("id") == req_id:
                    return msg.get("result", {}).get("cookies", [])
            except websocket.WebSocketTimeoutException:
                continue
        return []

def handle_google_popup():
    """Detects and automatically clicks the active account in Google OAuth popups."""
    time.sleep(2)
    targets = list_targets()
    google_tab = None
    for t in targets:
        if "accounts.google.com" in t.get("url", ""):
            google_tab = t
            break
            
    if not google_tab:
        return False
        
    print(f"[*] Detected Google OAuth popup: {google_tab.get('url')}")
    try:
        with CDPPage(google_tab.get("webSocketDebuggerUrl")) as gp:
            # Click the account chooser element
            click_js = """
            (() => {
                let el = document.querySelector('div[data-identifier], div[data-email], div[role="link"], li[data-authuser], div[data-item-index="0"]');
                if (el) {
                    el.click();
                    return "CLICKED_ACCOUNT";
                }
                // Check for Continue button
                let btn = document.querySelector('button, input[type="submit"]');
                if (btn) {
                    btn.click();
                    return "CLICKED_CONTINUE";
                }
                return "NOT_FOUND";
            })();
            """
            res = gp.evaluate(click_js, timeout=10)
            print(f"[*] Google Popup Action: {res}")
            time.sleep(3)
            return True
    except Exception as e:
        print(f"[!] Google popup handler error: {e}")
        return False

def scan_page_for_actions(page: CDPPage):
    js = """
    (() => {
        let items = [];
        let idCounter = 0;
        let all = document.querySelectorAll('button, a, div[role="button"], input[type="button"], input[type="submit"]');
        for (let el of all) {
            let rect = el.getBoundingClientRect();
            if (rect.width < 5 || rect.height < 5) continue;
            let text = (el.innerText || el.getAttribute('aria-label') || el.value || '').trim();
            if (!text) continue;
            
            if (!el.id) el.id = 'auto-btn-' + (++idCounter);
            items.push({
                id: el.id,
                tag: el.tagName.toLowerCase(),
                text: text.substring(0, 80)
            });
            if (items.length >= 60) break;
        }
        return items;
    })();
    """
    return page.evaluate(js) or []

def run_signup_for_target(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    clean_host = host.replace("www.", "")
    print("\n" + "=" * 60)
    print(f"[>] SIGNING UP ON: {clean_host} ({url})")
    print("=" * 60)
    
    # Use the first available page or create one
    targets = list_targets()
    page_target = None
    for t in targets:
        if t.get("type") == "page" and not t.get("url", "").startswith("chrome://"):
            page_target = t
            break
            
    if not page_target:
        res = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/new").read())
        ws_url = res.get("webSocketDebuggerUrl")
    else:
        ws_url = page_target.get("webSocketDebuggerUrl")
        
    with CDPPage(ws_url) as page:
        print(f"Navigating to {url}...")
        page.send("Page.navigate", {"url": url})
        time.sleep(6)
        
        # Step 1: Check if Google OAuth popup immediately opened or check page elements
        handle_google_popup()
        
        # Step 2: Scan page for Google sign-in buttons
        elements = scan_page_for_actions(page)
        print(f"Found {len(elements)} interactive buttons. Asking Master LLM to locate Google Sign In / Sign Up button...")
        
        prompt = f"""
We want to sign up or log in with Google on {url}.
Here are the buttons on the page:
{json.dumps(elements, indent=2)}

Find the button that represents:
1. "Continue with Google" / "Sign in with Google" / "Log in with Google" / "Google"
2. Or a "Sign In" / "Log In" / "Sign Up" / "Get Started" button that opens the login modal.

Respond with raw JSON:
{{
  "button_id": "string or null",
  "is_google": true or false,
  "reason": "explanation"
}}
"""
        try:
            resp = requests.post(
                OMNIROUTE_URL,
                headers={"Authorization": f"Bearer {OMNIROUTE_KEY}", "Content-Type": "application/json"},
                json={"model": OMNIROUTE_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
                timeout=30
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            decision = json.loads(content.strip())
        except Exception as e:
            print(f"LLM decision error: {e}")
            decision = {}
            
        btn_id = decision.get("button_id")
        if btn_id:
            print(f"Clicking #{btn_id} ({decision.get('reason')})...")
            click_js = f"""
            (() => {{
                let el = document.getElementById('{btn_id}');
                if (el) {{
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    el.style.outline = '4px solid #00f0ff';
                    el.style.boxShadow = '0 0 25px #00f0ff';
                    setTimeout(() => el.click(), 400);
                    return true;
                }}
                return false;
            }})();
            """
            page.evaluate(click_js)
            time.sleep(3)
            
            # Check if Google popup appeared
            handle_google_popup()
            time.sleep(6)
            
            # Re-check for inner Google button if a modal opened
            elements_2 = scan_page_for_actions(page)
            for el in elements_2:
                t_lower = el["text"].lower()
                if "google" in t_lower or "continue with google" in t_lower:
                    print(f"Found modal Google button: #{el['id']} ('{el['text']}'). Clicking...")
                    page.evaluate(f"document.getElementById('{el['id']}').click();")
                    time.sleep(3)
                    handle_google_popup()
                    break
                    
        print(f"Waiting 6s for authentication completion...")
        time.sleep(6)
        
        # Save session cookies & state
        cookies = page.get_cookies()
        print(f"Captured {len(cookies)} cookies for {clean_host}.")
        
        sess_file = SECRETS_DIR / f"session_{clean_host.replace('.', '_')}.json"
        existing = {}
        if sess_file.exists():
            try: existing = json.loads(sess_file.read_text(encoding="utf-8"))
            except: pass
            
        existing["host"] = clean_host
        existing["cookies"] = cookies
        existing["logged_in"] = len(cookies) > 0
        existing["updated_at"] = int(time.time())
        sess_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"[✓] Stored session credentials to {sess_file.name}")
        return True

def main():
    targets_file = pathlib.Path(r"D:\omniroute-monetizer\scripts\automation\target_sites.json")
    targets_data = json.loads(targets_file.read_text(encoding="utf-8"))
    
    # Run through all targets
    video_targets = targets_data.get("video_targets", [])
    chat_targets = targets_data.get("chat_targets", [])
    all_targets = video_targets + chat_targets
    
    print(f"Starting Google Sign-Up sweep across {len(all_targets)} providers on desktop Chrome...")
    for url in all_targets:
        try:
            run_signup_for_target(url)
            time.sleep(2)
        except Exception as e:
            print(f"Error processing {url}: {e}")

if __name__ == "__main__":
    main()
