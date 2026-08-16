#!/usr/bin/env python3
"""OpenRouter key generation (Tier C). Uses fresh storage_state.json.
Flow: New Key -> fill name -> Create -> capture plaintext key from reveal modal.
Secrets: full key written ONLY to state/generated_keys.json (gitignored);
terminal prints masked prefix only. T11-safe."""
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
OUT = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(OUT, exist_ok=True)

KEY_NAME = "omniroute-monetizer-" + time.strftime("%Y%m%d-%H%M")

def mask(k):
    if not k:
        return "<none>"
    return k[:10] + "..." + k[-4:] if len(k) > 16 else k[:4] + "..."

def load_keys():
    if os.path.exists(KEYS_FILE):
        try:
            return json.load(open(KEYS_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_key(provider, key, meta):
    data = load_keys()
    data[provider] = {"key": key, "name": KEY_NAME, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), **meta}
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# JS to find the revealed plaintext key anywhere in the DOM
FIND_KEY_JS = """() => {
    const candidates = [];
    const walk = (node) => {
        if (node.nodeType === 3) {
            const t = node.textContent.trim();
            if (/^sk-or-[A-Za-z0-9_\\-]{20,}$/.test(t)) candidates.push(t);
        } else if (node.nodeType === 1) {
            const v = node.value;
            if (v && /^sk-or-[A-Za-z0-9_\\-]{20,}$/.test(v.trim())) candidates.push(v.trim());
            for (const c of node.childNodes) walk(c);
        }
    };
    walk(document.body);
    // also check inputs and code/pre
    document.querySelectorAll('input, textarea, code, pre').forEach(el => {
        const t = (el.value || el.innerText || '').trim();
        if (/^sk-or-[A-Za-z0-9_\\-]{20,}$/.test(t)) candidates.push(t);
    });
    return candidates;
}"""

result = {"provider": "openrouter", "name": KEY_NAME, "status": "unknown"}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()
    try:
        page.goto("https://openrouter.ai/keys", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
        page.get_by_role("button", name="New Key").first.click(timeout=8000)
        page.wait_for_timeout(1500)
        page.fill("input#name", KEY_NAME)
        page.wait_for_timeout(800)
        # Create button becomes enabled after name fill
        create_btn = page.get_by_role("button", name="Create", exact=True).first
        create_btn.click(timeout=8000)
        page.wait_for_timeout(3000)
        # Look for the revealed key
        keys_found = page.evaluate(FIND_KEY_JS)
        if not keys_found:
            # maybe needs a moment / reveal step; dump dialog for inspection
            page.wait_for_timeout(2000)
            keys_found = page.evaluate(FIND_KEY_JS)
        if keys_found:
            key = keys_found[0]
            result["status"] = "captured"
            result["key_masked"] = mask(key)
            save_key("openrouter", key, {"source": "dom_create"})
            print(f"CAPTURED key: {mask(key)} (len={len(key)})")
        else:
            result["status"] = "no_key_found"
            # dump current DOM for diagnosis
            body = page.evaluate("() => document.body.innerText.slice(0, 2500)")
            result["body_sample"] = body
            print("NO KEY FOUND. Body sample:")
            print(body[:1500])
            with open(os.path.join(OUT, "openrouter_postcreate.json"), "w", encoding="utf-8") as f:
                json.dump({"url": page.url, "body": body}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print("ERROR:", result["error"])
    finally:
        browser.close()

print("\nRESULT:", json.dumps({k: v for k, v in result.items() if k != "body_sample"}, indent=2))
