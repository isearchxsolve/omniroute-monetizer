#!/usr/bin/env python3
"""Gemini key acquisition — two paths, human-assist fallback.

Path 1 (no creation, no 403 risk): harvest the EXISTING key already listed on
  aistudio.google.com/api-keys via its copy button (clipboard read).
Path 2: create a new key; if the create RPC 403s (bot-detection / quota),
  raise a human-assist flag and wait for the user to click Create in the
  visible Chrome window, then capture the revealed key.

Every candidate key is verified UPSTREAM (generativelanguage.googleapis.com,
HTTP 200 required) before saving. Full keys only in state/generated_keys.json
(gitignored); terminal prints masked values only. T11-safe.
"""
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signup_browser import ensure_chrome, attach, new_page  # noqa: E402
from human_assist import raise_flag, wait_for_clear  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
RECON_DIR = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(RECON_DIR, exist_ok=True)

APIKEYS_URL = "https://aistudio.google.com/api-keys"
KEY_RX = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
KEY_NAME = "omniroute-monetizer-" + time.strftime("%Y%m%d-%H%M")

import requests  # noqa: E402


def mask(k):
    if not k:
        return "<none>"
    return k[:8] + "..." + k[-4:] if len(k) > 14 else k[:4] + "..."


def verify_upstream(key: str):
    """Live-verify against the Gemini API. Returns (status_code, snippet)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        r = requests.get(url, timeout=30)
        return r.status_code, r.text[:200]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"[:200]


def save_key(provider, key, meta):
    data = {}
    if os.path.exists(KEYS_FILE):
        try:
            data = json.load(open(KEYS_FILE, encoding="utf-8"))
        except Exception:
            data = {}
    data[provider] = {"key": key, "name": meta.get("name", KEY_NAME),
                      "ts": time.strftime("%Y-%m-%d %H:%M:%S"), **meta}
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def grant_clipboard(page):
    """Grant clipboard-read permission via CDP so copy-button harvest works."""
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Browser.grantPermissions", {
            "origin": "https://aistudio.google.com",
            "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
        })
        return True
    except Exception:
        return False


def harvest_existing_key(page):
    """Path 1: click the copy button on the existing key row, read clipboard."""
    print("[*] Path 1: harvesting existing key via copy button ...")
    grant_clipboard(page)
    # Clear clipboard first so we know the read is fresh
    try:
        page.evaluate("() => navigator.clipboard.writeText('').catch(() => {})")
    except Exception:
        pass
    page.wait_for_timeout(500)

    clicked = page.evaluate(
        r"""() => {
            // find the copy button (content_copy icon button) in the keys table
            const btns = Array.from(document.querySelectorAll('button'));
            for (const b of btns) {
                const label = (b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '');
                if (/copy/i.test(label)) { b.click(); return label.trim().slice(0, 60); }
            }
            // fallback: mat-icon content_copy parent button
            const icons = Array.from(document.querySelectorAll('mat-icon'));
            for (const ic of icons) {
                if ((ic.innerText || '').trim() === 'content_copy') {
                    const b = ic.closest('button');
                    if (b) { b.click(); return 'icon:content_copy'; }
                }
            }
            return null;
        }"""
    )
    if not clicked:
        print("[-] no copy button found")
        return None
    print(f"[*] clicked copy button: {clicked}")
    page.wait_for_timeout(1500)

    clip = ""
    for _ in range(5):
        try:
            clip = page.evaluate("() => navigator.clipboard.readText().catch(() => '')") or ""
        except Exception:
            clip = ""
        if KEY_RX.search(clip):
            break
        page.wait_for_timeout(800)
    m = KEY_RX.search(clip or "")
    if m:
        return m.group(0)
    print(f"[-] clipboard did not yield a key (len={len(clip or '')})")
    return None


def create_new_key(page):
    """Path 2: create via dialog; return key or None (403 → caller raises flag)."""
    print("[*] Path 2: creating a new key via dialog ...")
    captured = []

    def _on_response(resp):
        try:
            if resp.status == 200:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" in ct or "proto" in ct or "batchexecute" in resp.url:
                    body = resp.text()
                    m = KEY_RX.search(body or "")
                    if m:
                        captured.append(m.group(0))
        except Exception:
            pass

    page.on("response", _on_response)
    try:
        page.get_by_role("button", name=re.compile("Create API key", re.I)).first.click(timeout=6000)
    except Exception as e:
        print("[-] no Create API key button:", str(e)[:80])
        return None
    page.wait_for_timeout(2500)

    try:
        dlg = page.locator("mat-dialog-container, [role=dialog]").first
        inp = dlg.locator("input").first
        if inp.is_visible(timeout=3000):
            inp.fill(KEY_NAME)
            page.wait_for_timeout(600)
    except Exception:
        pass

    try:
        page.get_by_role("button", name="Create key", exact=True).first.click(timeout=4000)
    except Exception:
        try:
            page.get_by_role("button", name=re.compile(r"^Create", re.I)).first.click(timeout=4000)
        except Exception as e:
            print("[-] confirm click failed:", str(e)[:80])
            return None

    for _ in range(16):
        page.wait_for_timeout(1500)
        if captured:
            return captured[0]
        dom_key = page.evaluate("() => { const m = document.body.innerText.match(/AIza[0-9A-Za-z_\\-]{35}/); return m ? m[0] : null; }")
        if dom_key:
            return dom_key
    return None


def human_assist_capture(page):
    """Path 3: human clicks Create in the visible window; we capture the reveal."""
    raise_flag(
        "gemini",
        APIKEYS_URL,
        "Create-key RPC returned 403 (likely bot-detection on automated click).",
        "In the open Chrome window: click 'Create API key' -> 'Create key' yourself. "
        "The script will capture the revealed key automatically.",
    )
    if not wait_for_clear("gemini", timeout_sec=900):
        return None
    # After human action, the key may be revealed in a modal or the table
    for _ in range(20):
        page.wait_for_timeout(1500)
        dom_key = page.evaluate("() => { const m = document.body.innerText.match(/AIza[0-9A-Za-z_\\-]{35}/); return m ? m[0] : null; }")
        if dom_key:
            return dom_key
        # try copy button again in case key landed in the table
        k = harvest_existing_key(page)
        if k:
            return k
    return None


def main():
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    result = {"provider": "gemini", "status": "unknown"}
    with sync_playwright() as pw:
        browser = attach(pw)
        page = new_page(browser, APIKEYS_URL)
        page.wait_for_timeout(5000)

        key = harvest_existing_key(page)
        source = "existing_copy_button"

        if not key:
            key = create_new_key(page)
            source = "dialog_create"

        if not key:
            key = human_assist_capture(page)
            source = "human_assist"

        if not key:
            result["status"] = "failed_all_paths"
            print(json.dumps(result, indent=2))
            return 1

        print(f"[*] candidate key {mask(key)} (source={source}); verifying upstream ...")
        status, body = verify_upstream(key)
        print(f"[*] upstream HTTP {status}")
        if status != 200:
            result.update({"status": "upstream_verify_failed", "http": status, "detail": body[:150], "key_masked": mask(key)})
            print("[-] key FAILED upstream verification — NOT saving/injecting (zero-fabrication rule)")
            print(json.dumps(result, indent=2))
            return 2

        save_key("gemini", key, {"source": source, "name": KEY_NAME})
        result.update({"status": "captured_and_verified", "key_masked": mask(key), "source": source})
        print(f"[+] gemini key VERIFIED upstream (200 OK) and saved: {mask(key)}")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
