"""
SSO Harvester Flow
Directly controls the operator's desktop Chrome on port 9222 to:
1. Navigate to target AI providers one by one.
2. Detect and click "Continue with Google" / "Sign in with Google".
3. Automatically select the logged-in Google account in the chooser popup.
4. Wait for the main studio workspace.
5. Input a prompt, click Generate, and intercept the network exchange into state/secrets/session_<host>.json.
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

class ChromeTab:
    def __init__(self, target_id=None, ws_url=None):
        self.target_id = target_id
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0

    def connect(self):
        if not self.ws_url:
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
            pages = [t for t in targets if t.get("type") == "page" and not t.get("url", "").startswith("chrome://")]
            if not pages:
                # create new target
                res = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/new").read())
                self.ws_url = res.get("webSocketDebuggerUrl")
                self.target_id = res.get("id")
            else:
                self.ws_url = pages[0].get("webSocketDebuggerUrl")
                self.target_id = pages[0].get("id")
                
        self.ws = websocket.create_connection(self.ws_url, timeout=25)
        self.send("Page.bringToFront")
        self.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        return self

    def close(self):
        if self.ws:
            try: self.ws.close()
            except: pass

    def __enter__(self):
        return self.connect()

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
                    result = msg.get("result", {}).get("result", {})
                    if "value" in result:
                        return result["value"]
                    if msg.get("result", {}).get("exceptionDetails"):
                        err = msg["result"]["exceptionDetails"].get("exception", {}).get("description", "JS Exception")
                        raise RuntimeError(f"JS threw: {err}")
                    return None
            except websocket.WebSocketTimeoutException:
                continue
        raise TimeoutError(f"Runtime.evaluate timed out after {timeout}s")

    def navigate(self, url, wait_seconds=4):
        self.send("Page.navigate", {"url": url})
        time.sleep(wait_seconds)

def find_elements_script():
    return """
    (() => {
        let items = [];
        let idCounter = 0;
        
        // Find Google login buttons, regular login buttons, prompt inputs, and generate buttons
        let all = document.querySelectorAll('button, a, input, textarea, div[role="button"], div[role="textbox"], div[contenteditable="true"]');
        for (let el of all) {
            let rect = el.getBoundingClientRect();
            if (rect.width < 5 || rect.height < 5 || rect.bottom < 0 || rect.top > window.innerHeight * 2) continue;
            
            let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
            if (!text && el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && !el.isContentEditable) continue;
            
            if (!el.id) {
                el.id = 'agent-el-' + (++idCounter);
            }
            
            items.push({
                id: el.id,
                tag: el.tagName.toLowerCase(),
                type: el.getAttribute('type') || '',
                role: el.getAttribute('role') || '',
                text: text.substring(0, 100),
                isEditable: el.isContentEditable || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
            });
            if (items.length >= 80) break;
        }
        return items;
    })();
    """

def ask_llm_for_action(elements, current_url):
    prompt = f"""
You are an autonomous browser agent on URL: {current_url}.
Here are the visible interactive elements on the page:
{json.dumps(elements, indent=2)}

Determine the SINGLE next best action:
1. If there is a Google Login / Continue with Google button, choose "CLICK_GOOGLE" with its element ID.
2. If there is an account selector (e.g. user's email/profile in Google chooser), choose "CLICK_ACCOUNT" with its ID.
3. If there is a prompt input and a generate/create/submit button:
   choose "GENERATE" with prompt_input_id and generate_button_id.
4. If there is a general Login / Sign Up / Start Free button, choose "CLICK_BUTTON" with its ID.

Respond with ONLY raw JSON:
{{
  "action": "CLICK_GOOGLE" | "CLICK_ACCOUNT" | "GENERATE" | "CLICK_BUTTON" | "NONE",
  "element_id": "string or null",
  "prompt_input_id": "string or null",
  "generate_button_id": "string or null",
  "reason": "brief explanation"
}}
"""
    try:
        resp = requests.post(
            OMNIROUTE_URL,
            headers={"Authorization": f"Bearer {OMNIROUTE_KEY}", "Content-Type": "application/json"},
            json={
                "model": OMNIROUTE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 400
            },
            timeout=30
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```json"): content = content[7:]
        if content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
        return json.loads(content.strip())
    except Exception as e:
        print(f"LLM decision failed: {e}")
        return {"action": "NONE"}

def execute_click(tab, el_id, color="#00ff88"):
    js = f"""
    (() => {{
        let el = document.getElementById('{el_id}');
        if (!el) return false;
        el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
        el.style.outline = '4px solid {color}';
        el.style.boxShadow = '0 0 25px {color}';
        setTimeout(() => el.click(), 400);
        return true;
    }})();
    """
    return tab.evaluate(js)

def execute_generate(tab, input_id, button_id, prompt_text="A serene cinematic 4k video of a forest in morning mist"):
    js = f"""
    (async () => {{
        let inputEl = document.getElementById('{input_id}');
        let buttonEl = document.getElementById('{button_id}');
        if (!inputEl || !buttonEl) return false;
        
        inputEl.scrollIntoView({{behavior: 'smooth', block: 'center'}});
        inputEl.style.outline = '4px solid #00f0ff';
        inputEl.focus();
        
        let val = {json.dumps(prompt_text)};
        if (inputEl.isContentEditable || inputEl.tagName === 'DIV' || inputEl.tagName === 'P') {{
            inputEl.innerText = val;
        }} else {{
            let proto = Object.getPrototypeOf(inputEl);
            let setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
            if (!setter) {{
                if (inputEl instanceof HTMLInputElement) setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                else if (inputEl instanceof HTMLTextAreaElement) setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
            }}
            if (setter) {{ try {{ setter.call(inputEl, val); }} catch(e) {{ inputEl.value = val; }} }}
            else {{ inputEl.value = val; }}
        }}
        
        inputEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
        inputEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
        inputEl.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, key: 'a' }}));
        
        await new Promise(r => setTimeout(r, 600));
        
        buttonEl.scrollIntoView({{behavior: 'smooth', block: 'center'}});
        buttonEl.style.outline = '4px solid #ff0055';
        await new Promise(r => setTimeout(r, 600));
        buttonEl.click();
        return true;
    }})();
    """
    return tab.evaluate(js)

def harvest_provider(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    print(f"\n============================================================")
    print(f"[*] STARTING PROVIDER: {host} ({url})")
    print(f"============================================================")
    
    with ChromeTab() as tab:
        tab.navigate(url, wait_seconds=5)
        
        for step in range(1, 5):
            curr_url = tab.evaluate("window.location.href") or url
            print(f"[Step {step}] Current URL: {curr_url}")
            
            # Extract DOM elements
            elements = tab.evaluate(find_elements_script()) or []
            print(f"[Step {step}] Extracted {len(elements)} interactive elements. Reasoning with Master LLM...")
            
            decision = ask_llm_for_action(elements, curr_url)
            action = decision.get("action", "NONE")
            reason = decision.get("reason", "")
            print(f"[Step {step}] LLM Decision: {action} ({reason})")
            
            if action in ("CLICK_GOOGLE", "CLICK_ACCOUNT", "CLICK_BUTTON"):
                el_id = decision.get("element_id")
                if el_id:
                    print(f"[Step {step}] Clicking {action} -> #{el_id}")
                    execute_click(tab, el_id)
                    time.sleep(4)
                    
            elif action == "GENERATE":
                inp_id = decision.get("prompt_input_id")
                btn_id = decision.get("generate_button_id")
                if inp_id and btn_id:
                    print(f"[Step {step}] Enabling network interception for 12s...")
                    tab.send("Network.enable")
                    while True:
                        tab.ws.settimeout(0.1)
                        try: tab.ws.recv()
                        except: break
                        
                    print(f"[Step {step}] Injecting prompt & clicking Generate -> input:#{inp_id}, btn:#{btn_id}")
                    execute_generate(tab, inp_id, btn_id)
                    
                    # Intercept generation network request
                    deadline = time.time() + 12
                    captured = None
                    while time.time() < deadline:
                        tab.ws.settimeout(1.0)
                        try:
                            msg = json.loads(tab.ws.recv())
                        except websocket.WebSocketTimeoutException:
                            continue
                            
                        if msg.get("method") == "Network.requestWillBeSent":
                            req = msg["params"]["request"]
                            req_url = req.get("url", "")
                            method = req.get("method", "GET")
                            is_tracker = any(k in req_url.lower() for k in (
                                "facebook.com", "google-analytics", "doubleclick", "datadoghq", 
                                "tiktok.com", "clarity.ms", "segment.io", "sentry.io", "mixpanel", 
                                "posthog", "/rum", "/telemetry", "/collect", "/events", "/tr/"
                            ))
                            if method in ("POST", "PUT") and not is_tracker and not any(ext in req_url.lower() for ext in (".png", ".jpg", ".js", ".css", ".svg", ".woff2")):
                                print(f"[!] CAPTURED GENERATION API: {method} {req_url[:80]}")
                                captured = req
                                break
                                
                    if captured:
                        clean_host = host.replace(".", "_")
                        sess_file = SECRETS_DIR / f"session_{clean_host}.json"
                        sess_data = {
                            "host": host,
                            "recorded_exchange": {
                                "method": captured.get("method"),
                                "url": captured.get("url"),
                                "headers": captured.get("headers"),
                                "post_data": captured.get("postData")
                            },
                            "updated_at": int(time.time())
                        }
                        sess_file.write_text(json.dumps(sess_data, indent=2), encoding="utf-8")
                        print(f"[✓] SUCCESS! Blueprint saved to {sess_file.name}")
                        return True
                    else:
                        print("[i] Generation clicked, no API intercepted.")
                        return True
            elif action == "NONE":
                print("[i] No further actions needed or page stable.")
                break
                
        return False

def main():
    targets_file = pathlib.Path(r"D:\omniroute-monetizer\scripts\automation\target_sites.json")
    targets_data = json.loads(targets_file.read_text(encoding="utf-8"))
    
    video_targets = targets_data.get("video_targets", [])
    chat_targets = targets_data.get("chat_targets", [])
    all_targets = video_targets + chat_targets
    
    print(f"Loaded {len(all_targets)} target providers ({len(video_targets)} video, {len(chat_targets)} chat).")
    
    for url in all_targets:
        try:
            harvest_provider(url)
            time.sleep(2)
        except Exception as e:
            print(f"Error on {url}: {e}")

if __name__ == "__main__":
    main()
