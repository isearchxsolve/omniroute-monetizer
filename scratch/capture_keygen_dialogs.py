#!/usr/bin/env python3
"""Open each provider's key-creation DIALOG (no final submit) and dump its
structure so we can write exact selectors for the mutating step. Read-only
w.r.t. key creation: opening the dialog does NOT create a key."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")
OUT = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(OUT, exist_ok=True)

SNAP_JS = """() => {
    const out = { url: location.href, buttons: [], inputs: [], headings: [], dialogs: [], body: '' };
    const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    document.querySelectorAll('[role="dialog"], dialog, [class*="modal" i], [class*="dialog" i], [class*="drawer" i]').forEach(el => {
        if (!vis(el)) return;
        out.dialogs.push({ tag: el.tagName, role: el.getAttribute('role'), text: (el.innerText||'').slice(0,400) });
    });
    document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(el => {
        if (!vis(el)) return;
        out.buttons.push({ text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0,80),
            id: el.id||null, aria: el.getAttribute('aria-label')||null, testid: el.getAttribute('data-testid')||null,
            type: el.type||null, disabled: el.disabled||null });
    });
    document.querySelectorAll('input, textarea, select').forEach(el => {
        out.inputs.push({ tag: el.tagName.toLowerCase(), type: el.type||null, name: el.name||null, id: el.id||null,
            placeholder: el.placeholder||null, aria: el.getAttribute('aria-label')||null,
            testid: el.getAttribute('data-testid')||null, visible: vis(el), value: (el.value||'').slice(0,20) });
    });
    document.querySelectorAll('h1,h2,h3,h4,label').forEach(el => { const t=(el.innerText||'').trim(); if(t&&vis(el)) out.headings.push(t.slice(0,80)); });
    out.body = (document.body.innerText||'').slice(0,1500);
    return out;
}"""

def dump(page, name):
    time.sleep(0.1)
    snap = page.evaluate(SNAP_JS)
    print(f"\n=== {name} DIALOG @ {snap['url'][:90]} ===")
    print(f"  headings: {snap['headings'][:8]}")
    print(f"  dialogs({len(snap['dialogs'])}):")
    for d in snap["dialogs"][:3]:
        print(f"    [{d['tag']}/{d['role']}] {d['text'][:160]!r}")
    print(f"  inputs({len(snap['inputs'])}):")
    for i in snap["inputs"]:
        print(f"    - {i['tag']} type={i['type']} name={i['name']} id={i['id']} ph={i['placeholder']!r} testid={i['testid']} vis={i['visible']}")
    print(f"  buttons({len(snap['buttons'])}):")
    for b in snap["buttons"]:
        print(f"    - text={b['text']!r} type={b['type']} testid={b['testid']} disabled={b['disabled']}")
    with open(os.path.join(OUT, f"{name}_dialog.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    return snap

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()

    # --- OpenRouter ---
    try:
        page.goto("https://openrouter.ai/keys", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
        page.get_by_role("button", name="New Key").first.click(timeout=8000)
        page.wait_for_timeout(2500)
        dump(page, "openrouter")
    except Exception as e:
        print(f"openrouter ERROR: {type(e).__name__}: {str(e)[:200]}")

    # --- Anthropic ---
    try:
        page.goto("https://platform.claude.com/settings/keys", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        page.get_by_role("button", name="Create key").first.click(timeout=8000)
        page.wait_for_timeout(2500)
        dump(page, "anthropic")
    except Exception as e:
        print(f"anthropic ERROR: {type(e).__name__}: {str(e)[:200]}")

    # --- GitHub ---
    try:
        page.goto("https://github.com/settings/tokens", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="Generate new token").first.click(timeout=8000)
        page.wait_for_timeout(2500)
        dump(page, "github")
    except Exception as e:
        print(f"github ERROR: {type(e).__name__}: {str(e)[:200]}")

    browser.close()
print("\ndone ->", OUT)
