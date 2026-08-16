#!/usr/bin/env python3
"""Debug: find exactly where AI Studio reveals the created Gemini key.

Registers a response listener that logs ALL response URLs + body snippets to a
file, clicks Create, then samples the DOM (including any open dialog) every
500ms for ~20s. Read-only w.r.t. secrets: full bodies go to a gitignored file,
terminal prints only masked/truncated info. T11-safe.
"""
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "automation"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from signup_browser import ensure_chrome, attach, new_page  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RECON_DIR = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(RECON_DIR, exist_ok=True)
NET_LOG = os.path.join(RECON_DIR, "gemini_net_responses.jsonl")
KEY_NAME = "omniroute-debug-" + time.strftime("%H%M%S")

APIKEY_URL = "https://aistudio.google.com/apikey"
KEY_RX = re.compile(r"AIza[0-9A-Za-z_\-]{35}")

net_records = []


def on_response(resp):
    try:
        url = resp.url
        status = resp.status
        ct = (resp.headers or {}).get("content-type", "")
        rec = {"url": url[:200], "status": status, "ct": ct[:60], "has_key": False, "body_snip": ""}
        # Only read bodies for likely-relevant responses
        if status == 200 and ("json" in ct or "proto" in ct or "batchexecute" in url or "key" in url.lower()):
            try:
                body = resp.text()
                m = KEY_RX.search(body or "")
                rec["has_key"] = bool(m)
                if m:
                    rec["key_masked"] = m.group(0)[:8] + "..." + m.group(0)[-4:]
                rec["body_snip"] = (body or "")[:400]
            except Exception as e:
                rec["body_err"] = str(e)[:80]
        net_records.append(rec)
        if rec["has_key"]:
            print(f"  [NET] KEY FOUND in response: {url[:80]}")
    except Exception:
        pass


def dump_dom(page, tag):
    try:
        info = {
            "tag": tag,
            "url": page.url,
            "dialogs": page.evaluate(
                """() => Array.from(document.querySelectorAll('mat-dialog-container, [role=dialog], .cdk-overlay-pane'))
                    .map(d => (d.innerText || '').slice(0, 600))"""
            ),
            "inputs": page.evaluate(
                """() => Array.from(document.querySelectorAll('input, textarea'))
                    .map(i => ({v: (i.value||'').slice(0,60), ph: i.placeholder||'', type: i.type||''}))
                    .filter(x => x.v || x.ph)"""
            ),
            "key_in_dom": bool(page.evaluate(
                "() => /AIza[0-9A-Za-z_\\-]{35}/.test(document.body.innerText)"
            )),
        }
        return info
    except Exception as e:
        return {"tag": tag, "err": str(e)[:100]}


def main():
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    with sync_playwright() as pw:
        browser = attach(pw)
        page = new_page(browser, APIKEY_URL)
        page.wait_for_timeout(5000)
        page.on("response", on_response)

        print("[*] Opening create dialog ...")
        try:
            page.get_by_role("button", name=re.compile("Create API key", re.I)).first.click(timeout=6000)
        except Exception as e:
            print("[-] could not click Create API key:", e)
            return
        page.wait_for_timeout(2500)

        # Fill name in dialog
        try:
            dlg = page.locator("mat-dialog-container, [role=dialog]").first
            inp = dlg.locator("input").first
            if inp.is_visible(timeout=3000):
                inp.fill(KEY_NAME)
                print(f"[*] filled name: {KEY_NAME}")
                page.wait_for_timeout(600)
        except Exception as e:
            print("[!] name fill skipped:", str(e)[:80])

        print("[*] Clicking 'Create key' and sampling DOM ...")
        try:
            page.get_by_role("button", name="Create key", exact=True).first.click(timeout=4000)
        except Exception:
            try:
                page.get_by_role("button", name=re.compile(r"^Create", re.I)).first.click(timeout=4000)
            except Exception as e:
                print("[-] could not click confirm:", e)

        # Rapid DOM sampling for 20s
        found = None
        for i in range(40):
            page.wait_for_timeout(500)
            info = dump_dom(page, f"t{i*0.5:.1f}s")
            if info.get("key_in_dom"):
                print(f"[+] KEY visible in DOM at {info['tag']}")
                found = info
                break
            if info.get("dialogs"):
                for d in info["dialogs"]:
                    m = KEY_RX.search(d)
                    if m:
                        print(f"[+] KEY in dialog at {info['tag']}")
                        found = info
                        break
            if found:
                break

        # Extract the key if found
        key = None
        if found:
            key = page.evaluate("() => { const m = document.body.innerText.match(/AIza[0-9A-Za-z_\\-]{35}/); return m ? m[0] : null; }")
            if not key:
                for d in found.get("dialogs", []):
                    m = KEY_RX.search(d)
                    if m:
                        key = m.group(0)
                        break

        # Also check network records
        if not key:
            for r in net_records:
                if r.get("has_key"):
                    m = KEY_RX.search(r.get("body_snip", ""))
                    if m:
                        key = m.group(0)
                        print("[+] recovered key from network record")
                        break

        # Persist diagnostics
        with open(NET_LOG, "w", encoding="utf-8") as f:
            for r in net_records:
                f.write(json.dumps(r) + "\n")
        with open(os.path.join(RECON_DIR, "gemini_debug_dom.json"), "w", encoding="utf-8") as f:
            json.dump({"found": found, "net_count": len(net_records),
                       "key_net_urls": [r["url"] for r in net_records if r.get("has_key")]}, f, indent=2)

        if key:
            # Save to generated_keys.json (gitignored)
            keys_file = os.path.join(ROOT, "state", "generated_keys.json")
            data = {}
            if os.path.exists(keys_file):
                try:
                    data = json.load(open(keys_file, encoding="utf-8"))
                except Exception:
                    data = {}
            data["gemini"] = {"key": key, "name": KEY_NAME, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "source": "aistudio_debug"}
            with open(keys_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[+] CAPTURED gemini key: {key[:8]}...{key[-4:]} (len={len(key)})")
        else:
            print("[-] key not found in DOM or network. See dumps:")
            print("    ", NET_LOG)
            print("    relevant net responses:")
            for r in net_records:
                if "key" in r["url"].lower() or "batchexecute" in r["url"] or r.get("body_snip"):
                    print(f"      {r['status']} {r['ct'][:20]:20s} {r['url'][:90]}")


if __name__ == "__main__":
    main()
