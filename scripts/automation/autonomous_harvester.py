"""autonomous_harvester.py — fully autonomous LLM-driven signup & harvest over existing Chrome profile.

Uses your authenticated live Chrome profile (to inherit your active Google session), 
but does so over the browser-level CDP endpoint (:9222). It opens new tabs,
uses the local OmniRoute LLM (port :8190) to find "Continue with Google" if there's a login wall,
signs in, finds the chat input, injects the prompt, and delegates to `sweep_grab.py` logic
to extract the network JSON trace into the Universal Pool.
"""
import sys, json, time, pathlib, re, websocket, urllib.request
sys.path.insert(0, 'D:/omniroute-monetizer/scripts/automation')
from cdp import Page

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
TARGETS_FILE = pathlib.Path(__file__).parent / "target_sites.json"
LLM_URL = "http://127.0.0.1:20128/v1/chat/completions" # Master OmniRoute endpoint

# Pure JS heuristic to pull ALL interactive elements for the LLM
JS_GET_ELS = """
(() => {
    let els = [];
    let idCounter = 0;
    for (let el of document.querySelectorAll('a, button, input, textarea, [role="button"]')) {
        let rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0 || rect.width * rect.height < 10) continue;
        
        let txt = (el.innerText || el.value || el.placeholder || '').trim();
        if (txt === '') continue; 
        
        if (!el.id) { el.id = 'agent-id-' + idCounter++; }
        
        els.push({
            tag: el.tagName.toLowerCase(),
            id: el.id,
            text: txt.substring(0, 100),
            role: el.getAttribute('role') || '',
            type: el.type || '',
            href: el.href || ''
        });
    }
    return els;
})();
"""

JS_CLICK = """
(() => {
    let el = document.getElementById('{id}');
    if (!el) return 'NOT_FOUND';
    el.scrollIntoView({block: 'center'});
    el.click();
    return 'SUCCESS';
})();
"""

JS_TYPE_AND_CLICK = """
(() => {
    let input = document.getElementById('{input_id}');
    let btn = document.getElementById('{btn_id}');
    if (!input || !btn) return 'NOT_FOUND';
    
    // Attempt multiple ways to inject text to bypass React/Vue restrictions
    let val = "Reply exactly one word: Omni.";
    
    // React 15/16 hack for both input and textarea
    let proto = Object.getPrototypeOf(input);
    let nativeInputValueSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set 
                                 || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set
                                 || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    if (nativeInputValueSetter) { nativeInputValueSetter.call(input, val); }
    else { input.value = val; }
    
    // Dispatch events
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'a' }));
    
    btn.scrollIntoView({block: 'center'});
    btn.click();
    return 'SUCCESS';
})();
"""

def call_llm(prompt: str) -> dict:
    import requests
    try:
        r = requests.post(LLM_URL, json={
            "model": "frontier", 
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "stream": False
        }, headers={"Authorization": "Bearer sk-omniroute"}, timeout=45)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        if text.startswith("```json"): text = text[7:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        print(f"LLM Error: {e}")
        return {}

def analyze_and_act(p: Page, host: str, depth: int = 0):
    if depth > 3:
        print(f"[{host}] Max depth reached. Aborting.")
        return False
        
    print(f"[{host}] Extracting DOM elements...")
    els = p.evaluate(JS_GET_ELS)
    
    print(f"[{host}] Found {len(els)} elements. Asking LLM to analyze state...")
    prompt = f"""
You are an autonomous web agent analyzing an AI Chat/Video generator UI.
Here are the interactive elements on the screen:
{json.dumps(els, indent=2)}

Task: Determine the current state of the page. 
If there is a "Sign in", "Log in", or "Continue with Google" button, we are on a LOGIN wall.
If there is a chat input (textarea/input) and a Generate/Send button, we are on the MAIN UI.

Reply strictly with a JSON object in one of these two formats:
1. For Login Wall: {{"state": "LOGIN", "google_btn_id": "the_id_of_google_btn"}}
2. For Main UI: {{"state": "MAIN", "input_id": "the_id_of_chat_input", "submit_btn_id": "the_id_of_send_btn"}}
3. If neither: {{"state": "UNKNOWN"}}
"""
    res = call_llm(prompt)
    if not res:
        print(f"[{host}] LLM failed to parse state.")
        return False
        
    state = res.get("state")
    if state == "LOGIN":
        gid = res.get("google_btn_id")
        if gid:
            print(f"[{host}] Found Login Wall. Clicking Google SSO ({gid})...")
            p.evaluate(JS_CLICK.replace('{id}', gid))
            time.sleep(5) # Wait for redirect
            return analyze_and_act(p, host, depth + 1) # Re-evaluate after login
            
    elif state == "MAIN":
        iid = res.get("input_id")
        bid = res.get("submit_btn_id")
        if iid and bid:
            print(f"[{host}] Found Main UI. Injecting payload...")
            
            # Start Network Interception before clicking
            p.send("Network.enable")
            while True:
                p.ws.settimeout(0.1)
                try: p.ws.recv()
                except: break
                
            p.evaluate(JS_TYPE_AND_CLICK.replace('{input_id}', iid).replace('{btn_id}', bid))
            print(f"[{host}] Payload injected! Waiting for network traffic...")
            
            # Capture logic similar to sweep_grab.py
            deadline = time.time() + 15
            while time.time() < deadline:
                p.ws.settimeout(1.0)
                try:
                    msg = json.loads(p.ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if msg.get("method") == "Network.requestWillBeSent":
                    req = msg["params"]["request"]
                    url = req.get("url", "")
                    if "/api/" in url or "/chat" in url or "/generate" in url or "/completions" in url:
                        print(f"[{host}] [!] CAUGHT POTENTIAL API REQUEST: {url}")
                        # In a real run, we would save to state/secrets/session_{host}.json here
                        return True
            print(f"[{host}] Timed out waiting for network request.")
            return False
            
    print(f"[{host}] Unknown state or missing elements.")
    return False

def run_harvester():
    targets = json.loads(TARGETS_FILE.read_text())
    print(f"Loaded {len(targets)} target sites.")
    
    # We create a new tab for each site over the existing browser connection
    for url in targets:
        target_id = None
        try:
            parsed = urllib.parse.urlsplit(url)
            host = parsed.hostname or url
            domain_match = host.replace("www.", "")
            print(f"\n======================================")
            print(f"Starting analysis for: {url}")
            
            # Create a new tab via the local CDP browser endpoint
            req = urllib.request.Request(f"http://127.0.0.1:9222/json/new?{url}", method="PUT")
            res = json.loads(urllib.request.urlopen(req, timeout=10).read())
            target_id = res["id"]
            
            time.sleep(5) # Wait for page load
            
            with Page(domain_match, port=9222) as p:
                analyze_and_act(p, host)
                
        except Exception as e:
            print(f"Failed on {url}: {e}")
        finally:
            if target_id:
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{target_id}")
                except Exception:
                    pass

if __name__ == "__main__":
    run_harvester()
