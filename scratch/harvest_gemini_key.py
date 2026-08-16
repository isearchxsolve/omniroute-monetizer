#!/usr/bin/env python3
"""Harvest Gemini API key(s) from the AI Studio page after human-assisted creation.

Human-in-the-loop pattern: the user completed the step that tripped bot detection
(403 on automated create). This script attaches to the running Chrome via CDP,
finds the open AI Studio tab, and extracts the plaintext key(s):
  1. Reveal modal still open -> key visible in DOM.
  2. Otherwise -> hook navigator.clipboard.writeText, click each row's copy
     button, capture what gets copied.

T11-safe: full keys written ONLY to state/generated_keys.json (gitignored);
terminal prints masked values only.
"""
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "automation"))

from signup_browser import ensure_chrome, attach  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
KEY_RX = re.compile(r"AIza[0-9A-Za-z_\-]{35}")

HOOK_JS = r"""() => {
    if (window.__keyCaptureInstalled) return 'already';
    window.__keyCaptureInstalled = true;
    window.__capturedClipboard = [];
    try {
        const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
        navigator.clipboard.writeText = (t) => {
            try { window.__capturedClipboard.push(String(t)); } catch (e) {}
            return orig(t);
        };
    } catch (e) { return 'hook_failed:' + e; }
    return 'hooked';
}"""

FIND_DOM_KEYS_JS = r"""() => {
    const out = new Set();
    const rx = /AIza[0-9A-Za-z_\-]{35}/;
    // dialogs first (reveal modal)
    const scopes = [
        ...Array.from(document.querySelectorAll('mat-dialog-container, [role=dialog], .cdk-overlay-pane')),
        document.body
    ];
    for (const scope of scopes) {
        const t = scope.innerText || '';
        let m;
        const re = new RegExp(rx.source, 'g');
        while ((m = re.exec(t)) !== null) out.add(m[0]);
    }
    document.querySelectorAll('input, textarea, code, pre').forEach(el => {
        const t = (el.value || el.innerText || '');
        const re = new RegExp(rx.source, 'g');
        let m;
        while ((m = re.exec(t)) !== null) out.add(m[0]);
    });
    return Array.from(out);
}"""


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def load_keys():
    if os.path.exists(KEYS_FILE):
        try:
            return json.load(open(KEYS_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main():
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    found = []
    with sync_playwright() as pw:
        browser = attach(pw)
        ctx = browser.contexts[0] if browser.contexts else None
        if not ctx:
            print("[-] no browser context")
            return 1

        # Find the AI Studio tab without disturbing it (reveal modal may be open)
        page = None
        for p in ctx.pages:
            try:
                if "aistudio.google.com" in p.url:
                    page = p
                    break
            except Exception:
                continue
        if page is None:
            print("[*] no AI Studio tab open; opening api keys page ...")
            page = ctx.new_page()
            page.goto("https://aistudio.google.com/apikey", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000)
        else:
            print(f"[*] using open tab: {page.url[:80]}")

        # 1) Direct DOM scan (catches open reveal modal)
        dom_keys = page.evaluate(FIND_DOM_KEYS_JS)
        if dom_keys:
            print(f"[+] found {len(dom_keys)} key(s) directly in DOM")
            found.extend(dom_keys)

        # 2) Clipboard-hook + copy-button sweep of the keys table
        hook_status = page.evaluate(HOOK_JS)
        print(f"[*] clipboard hook: {hook_status}")
        copy_btns = page.locator("button[aria-label*='copy' i], button:has-text('content_copy')")
        n = copy_btns.count()
        print(f"[*] copy buttons visible: {n}")
        for i in range(n):
            try:
                btn = copy_btns.nth(i)
                if not btn.is_visible():
                    continue
                btn.click()
                page.wait_for_timeout(900)
                captured = page.evaluate("() => window.__capturedClipboard || []")
                for c in captured:
                    m = KEY_RX.search(c or "")
                    if m and m.group(0) not in found:
                        found.append(m.group(0))
                        print(f"[+] captured via copy button #{i}: {mask(m.group(0))}")
                page.evaluate("() => { window.__capturedClipboard = []; }")
            except Exception as e:
                print(f"[!] copy button {i} failed: {str(e)[:80]}")

    # Dedupe, persist (gitignored file only)
    found = list(dict.fromkeys(found))
    if not found:
        print("[-] no keys harvested. FLAG: need human check of the AI Studio tab.")
        return 2

    data = load_keys()
    data["gemini"] = {
        "keys": found,
        "key": found[-1],  # newest row is usually last; verify step picks the valid one
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "aistudio_human_assisted_harvest",
    }
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\n[+] harvested {len(found)} gemini key(s):")
    for k in found:
        print(f"    {mask(k)} (len={len(k)})")
    print(f"[+] saved to state/generated_keys.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
