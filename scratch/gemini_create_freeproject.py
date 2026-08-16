#!/usr/bin/env python3
"""Attempt: create a Gemini key in a DIFFERENT project (free-tier / has credits).

The first harvested key is valid but bound to 'AI Video Monetizer' (prepay,
depleted). This opens the create dialog, enumerates the project dropdown,
selects a project other than 'AI Video Monetizer', creates, and captures the
key via network + DOM + clipboard hook.

T11-safe: full keys only to state/generated_keys.json; masked terminal output.
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
RECON_DIR = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(RECON_DIR, exist_ok=True)
KEY_RX = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
KEY_RX_NEW = re.compile(r"^[A-Z]{2}\.[0-9A-Za-z_\-]{20,}$")
KEY_NAME = "omniroute-free-" + time.strftime("%H%M%S")
AVOID_PROJECT = "AI Video Monetizer"

net_keys = []


def on_response(resp):
    try:
        if resp.status != 200:
            # log 403s for diagnosis
            if resp.status == 403:
                try:
                    net_keys.append({"err403": resp.url[:120], "body": (resp.text() or "")[:200]})
                except Exception:
                    net_keys.append({"err403": resp.url[:120]})
            return
        ct = (resp.headers or {}).get("content-type", "")
        if "json" in ct or "proto" in ct or "batchexecute" in resp.url:
            try:
                body = resp.text() or ""
                for rx in (KEY_RX,):
                    m = rx.search(body)
                    if m:
                        net_keys.append({"key": m.group(0), "url": resp.url[:80]})
            except Exception:
                pass
    except Exception:
        pass


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def main():
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    with sync_playwright() as pw:
        browser = attach(pw)
        ctx = browser.contexts[0] if browser.contexts else None
        page = None
        for p in (ctx.pages if ctx else []):
            try:
                if "aistudio.google.com" in p.url:
                    page = p
                    break
            except Exception:
                continue
        if page is None:
            page = ctx.new_page()
            page.goto("https://aistudio.google.com/apikey", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000)

        # Clear any leftover overlays/dialogs from previous runs
        for _ in range(3):
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
            except Exception:
                break
        page.wait_for_timeout(800)

        page.on("response", on_response)
        # clipboard hook
        page.evaluate(r"""() => {
            if (window.__keyCaptureInstalled) return;
            window.__keyCaptureInstalled = true;
            window.__capturedClipboard = [];
            const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
            navigator.clipboard.writeText = (t) => { try { window.__capturedClipboard.push(String(t)); } catch(e){} return orig(t); };
        }""")

        print("[*] opening create dialog ...")
        try:
            page.get_by_role("button", name=re.compile("Create API key", re.I)).first.click(timeout=6000)
        except Exception as e:
            print("[-] no Create API key button:", e)
            return 1
        page.wait_for_timeout(2500)

        # Enumerate project dropdown options
        dlg = page.locator("mat-dialog-container, [role=dialog]").first
        print("[*] looking for project selector in dialog ...")
        # The project selector is usually a mat-select. Click it to open options.
        options = []
        try:
            sel = dlg.locator("mat-select, [role=combobox], select").first
            if sel.is_visible(timeout=3000):
                sel.click()
                page.wait_for_timeout(1200)
                opts = page.locator("mat-option, [role=option]")
                for i in range(opts.count()):
                    t = (opts.nth(i).inner_text() or "").strip()
                    if t:
                        options.append(t)
                print(f"[*] project options: {options}")
        except Exception as e:
            print("[!] project selector not found:", str(e)[:80])

        # Pick a real project that is NOT the depleted one and NOT an action item.
        # Prefer "Default Gemini Project" (canonical free-tier project).
        picked = None
        try:
            opts = page.locator("mat-option, [role=option]")
            n = opts.count()
            texts = []
            for i in range(n):
                t = (opts.nth(i).inner_text() or "").strip().replace("\n", " ")
                texts.append(t)
            # rank: Default Gemini Project first, then any non-depleted real project
            def is_action(t):
                tl = t.lower()
                return "import project" in tl or "create project" in tl
            def is_depleted(t):
                return AVOID_PROJECT.lower() in t.lower()
            order = []
            for i, t in enumerate(texts):
                if is_action(t) or not t or is_depleted(t):
                    continue
                order.append((0 if "default gemini project" in t.lower() else 1, i, t))
            order.sort(key=lambda x: x[0])
            if order:
                _, idx, label = order[0]
                opts.nth(idx).click()
                picked = label
                print(f"[*] selected project: {picked}")
            else:
                print(f"[!] no usable project (options={texts})")
        except Exception as e:
            print("[!] option selection failed:", str(e)[:80])

        page.wait_for_timeout(1000)

        # Fill name
        try:
            inp = dlg.locator("input").first
            if inp.is_visible(timeout=2000):
                inp.fill(KEY_NAME)
                page.wait_for_timeout(500)
        except Exception:
            pass

        print("[*] clicking Create key ...")
        try:
            page.get_by_role("button", name="Create key", exact=True).first.click(timeout=4000)
        except Exception:
            try:
                page.get_by_role("button", name=re.compile(r"^Create", re.I)).first.click(timeout=4000)
            except Exception as e:
                print("[-] confirm click failed:", e)

        # Capture loop: DOM + clipboard for up to 20s
        key = None
        for i in range(40):
            page.wait_for_timeout(500)
            # DOM
            try:
                m = page.evaluate("() => { const m = document.body.innerText.match(/AIza[0-9A-Za-z_\\-]{35}/); return m ? m[0] : null; }")
                if m:
                    key = m
                    print(f"[+] key in DOM at {i*0.5:.1f}s")
                    break
            except Exception:
                pass
            # clipboard
            try:
                caps = page.evaluate("() => window.__capturedClipboard || []")
                for c in caps:
                    mm = KEY_RX.search(c or "")
                    if mm:
                        key = mm.group(0)
                        break
                    if KEY_RX_NEW.match((c or "").strip()):
                        key = c.strip()
                        break
                if key:
                    print(f"[+] key via clipboard at {i*0.5:.1f}s")
                    break
                page.evaluate("() => { window.__capturedClipboard = []; }")
            except Exception:
                pass
            # network
            for rec in net_keys:
                if rec.get("key"):
                    key = rec["key"]
                    break
            if key:
                break

        # dump diagnostics
        with open(os.path.join(RECON_DIR, "gemini_freeproject_net.json"), "w", encoding="utf-8") as f:
            json.dump(net_keys, f, indent=2)

        if not key:
            e403 = [r for r in net_keys if r.get("err403")]
            print("[-] no key captured.")
            if e403:
                print("    403 responses (likely bot-detection on create RPC):")
                for r in e403[:3]:
                    print(f"      {r['err403']}")
                    print(f"        {r.get('body','')[:150]}")
            print("FLAG: automated create blocked. Human assist needed.")
            return 2

        # save
        data = {}
        if os.path.exists(KEYS_FILE):
            try:
                data = json.load(open(KEYS_FILE, encoding="utf-8"))
            except Exception:
                data = {}
        entry = data.get("gemini", {})
        keys = entry.get("keys", [])
        if key not in keys:
            keys.append(key)
        data["gemini"] = {"keys": keys, "key": key, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "source": "aistudio_freeproject_create", "project": picked}
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[+] CAPTURED key {mask(key)} (project={picked}); saved.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
