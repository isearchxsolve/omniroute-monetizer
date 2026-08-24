#!/usr/bin/env python3
"""auto_generate_agent.py -- LLM-driven CDP auto-generator for the video pool.

Connects to all open video provider tabs in the target browser,
uses an LLM to identify the prompt input and generate button,
and orchestrates the generation action via CDP. This forces the
tab to fire real backend requests that sweep_grab.py intercepts.

Usage:
  python auto_generate_agent.py [--port 9222] [--prompt "A red fox..."]
"""
import argparse
import json
import requests
import sys
import time

from cdp import Page, list_targets, DEFAULT_PORT

JS_GET_ELS = """
(() => {
    let els = [];
    let idCounter = 0;
    
    // Only select explicit interactive elements, no generic divs
    let selectors = 'textarea, input[type="text"], input[type="search"], input:not([type]), button, [role="button"], [role="textbox"], [contenteditable="true"]';
    
    for (let el of document.querySelectorAll(selectors)) {
        let rect = el.getBoundingClientRect();
        // Skip invisible
        if (rect.width === 0 || rect.height === 0 || rect.width * rect.height < 10) continue;
        
        let tag = el.tagName.toLowerCase();
        let role = el.getAttribute('role') || '';
        let aria = el.getAttribute('aria-label') || '';
        let txt = (el.innerText || el.value || el.placeholder || aria).trim();
        
        // If it has absolutely no text or label, we can't identify it, so skip it to save LLM context
        if (txt === '') continue;
        
        if (!el.id) {
            el.id = 'llm-agent-temp-id-' + idCounter++;
        }
        
        let cls = typeof el.className === 'string' ? el.className : '';
        els.push({
            tag: tag,
            id: el.id,
            placeholder: el.placeholder || '',
            text: txt.substring(0, 100),
            class: cls,
            type: el.type || '',
            role: role
        });
    }
    return els;
})();
"""

JS_EXECUTE_ACTION = """
(async () => {
    let inputEl = document.getElementById('{input_id}');
    let buttonEl = document.getElementById('{button_id}');
    
    if (!inputEl || !buttonEl) {
        return "ELEMENT_NOT_FOUND";
    }
    
    // Fill prompt
    inputEl.focus();
    inputEl.value = {prompt_json};
    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
    
    await new Promise(r => setTimeout(r, 500));
    
    // Click button
    buttonEl.scrollIntoView({block: 'center'});
    buttonEl.click();
    return "SUCCESS";
})();
"""

def extract_and_identify(page: Page, title: str):
    print(f"[{title}] Injecting extraction script...")
    try:
        els = page.evaluate(JS_GET_ELS, timeout=15)
    except Exception as e:
        print(f"[{title}] Failed to extract elements: {e}")
        return None, None
        
    if not els:
        print(f"[{title}] No interactive elements found.")
        return None, None
        
    print(f"[{title}] Extracted {len(els)} elements. Asking local LLM...")
    prompt = f"""
You are an AI agent controlling a web browser. I want to generate an AI video OR send a chat message to an AI.
Here is a list of interactive elements on the page (represented as JSON):
{json.dumps(els, indent=2)}

Identify:
1. The text input element (or textarea) where I should type my prompt or chat message.
2. The button element I should click to generate the video OR send the chat message (e.g. Generate, Create, Send, Submit, or an arrow icon).

Reply strictly with a JSON object in this format (and nothing else):
{{
    "input_id": "the_id_of_the_input",
    "button_id": "the_id_of_the_button"
}}
"""
    try:
        r = requests.post("http://127.0.0.1:8190/v1/chat/completions", json={
            "model": "auto/pro-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0.0,
            "stream": False
        }, timeout=30)
        r.raise_for_status()
        res_text = r.json()["choices"][0]["message"]["content"].strip()
        # Clean markdown if present
        if res_text.startswith("```json"):
            res_text = res_text[7:]
        if res_text.endswith("```"):
            res_text = res_text[:-3]
        
        data = json.loads(res_text.strip())
        return data.get("input_id"), data.get("button_id")
    except Exception as e:
        print(f"[{title}] LLM request failed: {e}. Raw response:\n{res_text if 'res_text' in locals() else 'None'}\n---")
        return None, None

def run_tab(target, prompt_text: str, port: int):
    title = target.get("title", "")[:30]
    try:
        with Page(target.get("url"), port=port, timeout=30) as p:
            input_id, button_id = extract_and_identify(p, title)
            if not input_id or not button_id:
                print(f"[{title}] LLM could not identify elements. Skipping.")
                return False
                
            print(f"[{title}] LLM identified input='{input_id}', button='{button_id}'")
            
            # Execute
            js = JS_EXECUTE_ACTION.replace('{input_id}', input_id).replace('{button_id}', button_id)
            js = js.replace('{prompt_json}', json.dumps(prompt_text))
            
            res = p.evaluate(js, timeout=20)
            if res == "SUCCESS":
                print(f"[{title}] Successfully triggered generation.")
                return True
            else:
                print(f"[{title}] CDP execution failed: {res}")
                return False
    except BaseException as e:
        print(f"[{title}] Error connecting/evaluating: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--prompt", type=str, default="A cinematic 4k highly detailed video of a red fox running through snow")
    args = parser.parse_args()
    
    print(f"Fetching targets on port {args.port}...")
    try:
        targets = [t for t in list_targets(args.port) if t.get("type") == "page" and not t.get("url", "").startswith("devtools://")]
    except Exception as e:
        print(f"Failed to list targets: {e}")
        sys.exit(1)
        
    print(f"Found {len(targets)} page targets. Starting agent sequence...")
    
    success_count = 0
    for t in targets:
        # Ignore empty pages
        if t.get("url") == "about:blank":
            continue
            
        print("-" * 60)
        if run_tab(t, args.prompt, args.port):
            success_count += 1
        time.sleep(2)
        
    print("=" * 60)
    print(f"Auto-generation triggered on {success_count}/{len(targets)} tabs.")

if __name__ == "__main__":
    main()
