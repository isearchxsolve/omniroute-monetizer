#!/usr/bin/env python3
"""GitHub classic PAT generation (Tier C).
Flow: /settings/tokens/new -> fill note -> no-expiration -> repo scope ->
Generate token -> capture ghp_/github_pat_ token. Handles possible sudo wall.
Secrets only to state/generated_keys.json."""
import json, os, re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
OUT = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(OUT, exist_ok=True)

KEY_NAME = "omniroute-monetizer-" + time.strftime("%Y%m%d-%H%M")

def mask(k):
    if not k:
        return "<none>"
    return k[:8] + "..." + k[-4:] if len(k) > 14 else k[:4] + "..."

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

FIND_TOKEN_JS = """() => {
    const candidates = [];
    const re = /^(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{30,})$/;
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

result = {"provider": "github", "name": KEY_NAME, "status": "unknown"}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()
    try:
        page.goto("https://github.com/settings/tokens/new", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        # sudo wall check on entry
        if "sudo" in page.url.lower() or page.locator('input[type="password"]').count() > 0:
            result["status"] = "sudo_wall"
            result["url"] = page.url
            print("[!] SUDO/PASSWORD WALL at", page.url)
        else:
            page.fill("input#oauth_access_description", KEY_NAME)
            page.wait_for_timeout(500)
            # expiration -> No expiration
            try:
                page.select_option("select#oauth_access_expires_at", "no_expiration")
                print("[*] expiration set to No expiration")
            except Exception as e:
                print("[*] expiration select fallback:", e)
                try:
                    page.select_option("select#oauth_access_expires_at", index=0)
                except Exception:
                    pass
            page.wait_for_timeout(500)
            # repo scope
            try:
                page.check("input#repo")
                print("[*] repo scope checked")
            except Exception as e:
                print("[*] repo scope check failed:", e)
            page.wait_for_timeout(500)
            # submit
            page.get_by_role("button", name="Generate token").first.click(timeout=8000)
            page.wait_for_timeout(3500)
            # sudo wall after submit?
            if "sudo" in page.url.lower() or page.locator('input[type="password"]').count() > 0:
                result["status"] = "sudo_wall_after_submit"
                result["url"] = page.url
                print("[!] SUDO/PASSWORD WALL after submit at", page.url)
            else:
                tokens = page.evaluate(FIND_TOKEN_JS)
                if not tokens:
                    page.wait_for_timeout(2500)
                    tokens = page.evaluate(FIND_TOKEN_JS)
                if tokens:
                    key = tokens[0]
                    result["status"] = "captured"
                    result["key_masked"] = mask(key)
                    save_key("github", key, {"source": "dom_create", "scope": "repo"})
                    print(f"CAPTURED token: {mask(key)} (len={len(key)})")
                else:
                    result["status"] = "no_token_found"
                    body = page.evaluate("() => document.body.innerText.slice(0, 2000)")
                    result["body_sample"] = body
                    result["url"] = page.url
                    print("NO TOKEN FOUND. URL:", page.url)
                    print(body[:1200])
                    with open(os.path.join(OUT, "github_postcreate.json"), "w", encoding="utf-8") as f:
                        json.dump({"url": page.url, "body": body}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print("ERROR:", result["error"])
    finally:
        browser.close()

print("\nRESULT:", json.dumps({k: v for k, v in result.items() if k != "body_sample"}, indent=2))
