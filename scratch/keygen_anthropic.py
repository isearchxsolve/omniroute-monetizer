#!/usr/bin/env python3
"""Anthropic key generation (Tier C) on platform.claude.com.
Flow: Create key -> fill name -> (pick expiration if required) -> Add ->
capture plaintext key from reveal. Secrets only to state/generated_keys.json."""
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
    return k[:12] + "..." + k[-4:] if len(k) > 18 else k[:4] + "..."

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

FIND_KEY_JS = """() => {
    const candidates = [];
    const re = /^sk-ant-[A-Za-z0-9_\\-]{20,}$/;
    document.querySelectorAll('input, textarea, code, pre').forEach(el => {
        const t = (el.value || el.innerText || '').trim();
        if (re.test(t)) candidates.push(t);
    });
    const walk = (node) => {
        if (node.nodeType === 3) {
            const t = node.textContent.trim();
            if (re.test(t)) candidates.push(t);
        } else if (node.nodeType === 1) {
            for (const c of node.childNodes) walk(c);
        }
    };
    walk(document.body);
    return candidates;
}"""

result = {"provider": "anthropic", "name": KEY_NAME, "status": "unknown"}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()
    try:
        page.goto("https://platform.claude.com/settings/keys", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        page.get_by_role("button", name="Create key").first.click(timeout=8000)
        page.wait_for_timeout(2000)
        dlg = page.locator('[role="dialog"]').first
        # name input inside dialog (placeholder 'my-secret-key')
        name_input = dlg.locator('input[placeholder="my-secret-key"]').first
        name_input.fill(KEY_NAME)
        page.wait_for_timeout(800)
        add_btn = dlg.locator('button[type="submit"]').first
        if add_btn.is_disabled():
            # expiration is required — it's a role=combobox, not a button
            print("[*] Add disabled; selecting an expiration...")
            exp_btn = dlg.locator('[role="combobox"]:has-text("Select an expiration")').first
            exp_btn.click(timeout=5000)
            page.wait_for_timeout(1200)
            # dump available options
            opts = page.locator('[role="option"], [role="menuitem"], [role="listbox"] li').all()
            print(f"[*] options visible: {len(opts)}")
            chosen = False
            for opt_name in ("No expiration", "Never", "1 day", "7 days", "30 days", "90 days", "1 year"):
                try:
                    page.get_by_role("option", name=re.compile(opt_name, re.I)).first.click(timeout=2500)
                    print(f"[*] selected expiration: {opt_name}")
                    chosen = True
                    break
                except Exception:
                    continue
            if not chosen:
                # fallback: click first option-like element
                for o in opts:
                    try:
                        t = o.inner_text().strip()
                        if t:
                            o.click(timeout=2500)
                            print(f"[*] selected expiration (fallback): {t[:40]}")
                            chosen = True
                            break
                    except Exception:
                        continue
            page.wait_for_timeout(800)
        if add_btn.is_disabled():
            result["status"] = "add_still_disabled"
            body = page.evaluate("() => document.body.innerText.slice(0, 2000)")
            result["body_sample"] = body
            print("[-] Add still disabled. Body:")
            print(body[:1200])
        else:
            add_btn.click(timeout=8000)
            page.wait_for_timeout(3000)
            keys_found = page.evaluate(FIND_KEY_JS)
            if not keys_found:
                page.wait_for_timeout(2500)
                keys_found = page.evaluate(FIND_KEY_JS)
            if keys_found:
                key = keys_found[0]
                result["status"] = "captured"
                result["key_masked"] = mask(key)
                save_key("anthropic", key, {"source": "dom_create"})
                print(f"CAPTURED key: {mask(key)} (len={len(key)})")
            else:
                result["status"] = "no_key_found"
                body = page.evaluate("() => document.body.innerText.slice(0, 2500)")
                result["body_sample"] = body
                print("NO KEY FOUND. Body sample:")
                print(body[:1500])
                with open(os.path.join(OUT, "anthropic_postcreate.json"), "w", encoding="utf-8") as f:
                    json.dump({"url": page.url, "body": body}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print("ERROR:", result["error"])
    finally:
        browser.close()

print("\nRESULT:", json.dumps({k: v for k, v in result.items() if k != "body_sample"}, indent=2))
