#!/usr/bin/env python3
"""Autonomous signup adapter: Google AI Studio (Gemini) API key.

Blueprint Module 2+3 implementation for the `gemini` provider:
  - Uses the existing logged-in Google session in the plain-Chrome profile
    (no OTP/CAPTCHA expected 99% of the time per user observation).
  - Navigates to https://aistudio.google.com/apikey
  - Clicks "Create API key", picks/creates a Cloud project, captures the
    revealed plaintext key (AIza...).
  - Full key written ONLY to state/generated_keys.json (gitignored).
    Terminal/logs print masked values only (T11-safe).

Modes:
  --recon   read-only: attach, navigate, dump page state for selector design
  (default) full run: create key + capture
"""
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signup_browser import ensure_chrome, attach, new_page  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
RECON_DIR = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(RECON_DIR, exist_ok=True)

APIKEY_URL = "https://aistudio.google.com/apikey"
KEY_NAME = "omniroute-monetizer-" + time.strftime("%Y%m%d-%H%M")

# Revealed Gemini keys match AIza[0-9A-Za-z_-]{35}
FIND_KEY_JS = r"""() => {
    const out = new Set();
    const rx = /AIza[0-9A-Za-z_\-]{35}/;
    const walk = (node) => {
        if (node.nodeType === 3) {
            const t = node.textContent.trim();
            if (rx.test(t)) out.add(t.match(rx)[0]);
        } else if (node.nodeType === 1) {
            const v = node.value || node.getAttribute && node.getAttribute('data-clipboard-text');
            if (v && rx.test(v)) out.add(v.match(rx)[0]);
            for (const c of node.childNodes) walk(c);
        }
    };
    walk(document.body);
    document.querySelectorAll('input, textarea, code, pre').forEach(el => {
        const t = (el.value || el.innerText || '').trim();
        const m = t.match(rx);
        if (m) out.add(m[0]);
    });
    return Array.from(out);
}"""


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


def dump_state(page, tag):
    """Read-only recon dump: URL, title, visible buttons/links, body sample."""
    state = {
        "tag": tag,
        "url": page.url,
        "title": page.title(),
        "buttons": [],
        "links": [],
        "body_sample": "",
    }
    try:
        state["buttons"] = page.evaluate(
            """() => Array.from(document.querySelectorAll('button, [role=button], a.mat-mdc-button'))
                .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())
                .filter(t => t && t.length < 80).slice(0, 60)"""
        )
        state["links"] = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href).filter(h => h && !h.startsWith('javascript')).slice(0, 40)"""
        )
        state["body_sample"] = page.evaluate("() => document.body.innerText.slice(0, 2000)")
    except Exception as e:  # noqa: BLE001
        state["eval_error"] = str(e)[:200]
    path = os.path.join(RECON_DIR, f"gemini_{tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"[*] recon dump -> {path}")
    print(f"    url={state['url']} title={state['title']!r}")
    print(f"    buttons={state['buttons'][:25]}")
    print(f"    body[:300]={state['body_sample'][:300]!r}")
    return state


def handle_google_account_chooser(page):
    """If redirected to accounts.google.com, pick the existing logged-in account."""
    if "accounts.google.com" not in page.url:
        return False
    print("[*] Google account chooser detected; selecting existing account ...")
    # The chooser lists accounts as buttons/links containing an email address.
    picked = page.evaluate(
        r"""() => {
            const els = Array.from(document.querySelectorAll('[data-email], [data-identifier], li, button, a, div[role=link]'));
            for (const el of els) {
                const email = el.getAttribute && (el.getAttribute('data-email') || el.getAttribute('data-identifier'));
                if (email && /@/.test(email)) { el.click(); return email; }
            }
            for (const el of els) {
                const t = (el.innerText || '').trim();
                const m = t.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
                if (m) { el.click(); return m[0]; }
            }
            return null;
        }"""
    )
    if picked:
        print(f"[*] clicked account: {picked}")
        page.wait_for_timeout(4000)
        return True
    print("[!] account chooser present but no account element found")
    return False


def run(recon_only=False):
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    result = {"provider": "gemini", "mode": "recon" if recon_only else "create", "status": "unknown"}
    with sync_playwright() as pw:
        browser = attach(pw)
        page = new_page(browser, APIKEY_URL)
        page.wait_for_timeout(5000)

        # Google SSO redirect handling (up to 2 hops)
        for _ in range(2):
            if handle_google_account_chooser(page):
                page.wait_for_timeout(3000)

        dump_state(page, "apikey_page")

        if recon_only:
            result["status"] = "recon_done"
            print(json.dumps(result, indent=2))
            return result

        # --- Create key flow ---
        # Button text variants seen across AI Studio versions
        create_clicked = False
        for label in ("Create API key", "Create API Key", "Get API key", "Create key"):
            try:
                btn = page.get_by_role("button", name=re.compile(label, re.I)).first
                btn.click(timeout=4000)
                create_clicked = True
                print(f"[*] clicked '{label}'")
                break
            except Exception:
                continue
        if not create_clicked:
            # fallback: any button containing 'API key'
            clicked = page.evaluate(
                r"""() => {
                    const bs = Array.from(document.querySelectorAll('button, [role=button]'));
                    for (const b of bs) {
                        if (/api\s*key/i.test(b.innerText || '')) { b.click(); return (b.innerText||'').trim(); }
                    }
                    return null;
                }"""
            )
            if clicked:
                create_clicked = True
                print(f"[*] fallback clicked button: {clicked}")
        if not create_clicked:
            result["status"] = "no_create_button"
            dump_state(page, "no_create_button")
            print(json.dumps(result, indent=2))
            return result

        page.wait_for_timeout(3000)
        dump_state(page, "post_create_click")

        # Dialog: "Create a new key" — fill the name field, then click "Create key".
        # Also listen for the backend response that returns the plaintext key.
        captured_from_network = []

        def _on_response(resp):
            try:
                if resp.status != 200:
                    return
                ct = (resp.headers or {}).get("content-type", "")
                # AI Studio uses RPC-style endpoints; scan any text/json/proto body
                if any(t in ct for t in ("json", "proto", "text")) or "batchexecute" in resp.url:
                    text = resp.text()
                    m = re.search(r"AIza[0-9A-Za-z_\-]{35}", text or "")
                    if m:
                        captured_from_network.append(m.group(0))
            except Exception:
                pass

        page.on("response", _on_response)

        # Fill "Name your key" input if present (scoped to the open dialog)
        try:
            dialog = page.locator("mat-dialog-container, [role=dialog]").first
            name_input = dialog.locator("input").first
            if name_input.is_visible(timeout=3000):
                name_input.fill(KEY_NAME)
                print(f"[*] filled key name: {KEY_NAME}")
                page.wait_for_timeout(800)
        except Exception:
            pass

        # Click the dialog's confirm button (exact "Create key" preferred)
        confirmed = False
        for label in ("Create key", "Create API key in new project", "Create API key in existing project"):
            try:
                page.get_by_role("button", name=label, exact=True).first.click(timeout=3000)
                print(f"[*] confirmed: '{label}'")
                confirmed = True
                break
            except Exception:
                continue
        if not confirmed:
            try:
                page.get_by_role("button", name=re.compile(r"^Create", re.I)).first.click(timeout=3000)
                print("[*] confirmed via regex ^Create")
                confirmed = True
            except Exception:
                pass

        # Wait for the key reveal (DOM or network capture)
        keys_found = []
        for i in range(16):
            page.wait_for_timeout(2500)
            keys_found = page.evaluate(FIND_KEY_JS) or captured_from_network
            if keys_found:
                break
            # If a reveal modal appeared with a copy button, try clipboard route
            if i == 4:
                try:
                    copy_btn = page.get_by_role("button", name=re.compile("copy", re.I)).first
                    if copy_btn.is_visible(timeout=1500):
                        copy_btn.click()
                        page.wait_for_timeout(1200)
                        clip = page.evaluate("() => navigator.clipboard.readText().catch(() => '')")
                        if clip and re.search(r"AIza[0-9A-Za-z_\-]{35}", clip):
                            keys_found = [re.search(r"AIza[0-9A-Za-z_\-]{35}", clip).group(0)]
                            break
                except Exception:
                    pass
        if keys_found:
            key = keys_found[0]
            result["status"] = "captured"
            result["key_masked"] = mask(key)
            save_key("gemini", key, {"source": "aistudio_dom_create"})
            print(f"[+] CAPTURED gemini key: {mask(key)} (len={len(key)})")
        else:
            result["status"] = "no_key_found"
            dump_state(page, "post_create_nokey")
        print(json.dumps({k: v for k, v in result.items()}, indent=2))
    return result


if __name__ == "__main__":
    run(recon_only="--recon" in sys.argv)
