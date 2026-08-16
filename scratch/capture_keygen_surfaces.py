#!/usr/bin/env python3
"""Read-only capture of the CURRENT key-creation surfaces using the fresh
storage_state.json. No key-creating clicks. Dumps buttons/inputs/dialog structure
so we can write correct selectors. T11-safe (no secrets printed)."""
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

SURFACES = [
    ("openrouter", "https://openrouter.ai/keys"),
    ("anthropic", "https://platform.claude.com/settings/keys"),
    ("github", "https://github.com/settings/tokens"),
]

SNAPSHOT_JS = """() => {
    const out = { title: document.title, url: location.href, buttons: [], inputs: [], links: [], headings: [], dialogs: [] };
    const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(el => {
        if (!vis(el)) return;
        out.buttons.push({
            text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 80),
            id: el.id || null,
            aria: el.getAttribute('aria-label') || null,
            dataTestid: el.getAttribute('data-testid') || null,
        });
    });
    document.querySelectorAll('input, textarea, select').forEach(el => {
        if (!vis(el)) return;
        out.inputs.push({
            tag: el.tagName.toLowerCase(), type: el.type || null, name: el.name || null,
            id: el.id || null, placeholder: el.placeholder || null,
            aria: el.getAttribute('aria-label') || null, dataTestid: el.getAttribute('data-testid') || null,
        });
    });
    document.querySelectorAll('a[href]').forEach(el => {
        if (!vis(el)) return;
        const t = (el.innerText || '').trim().slice(0, 60);
        if (t) out.links.push({ text: t, href: el.href.slice(0, 120) });
    });
    document.querySelectorAll('h1,h2,h3').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t) out.headings.push(t.slice(0, 100));
    });
    document.querySelectorAll('[role="dialog"], dialog, .modal, [class*="modal" i], [class*="dialog" i]').forEach(el => {
        if (!vis(el)) return;
        out.dialogs.push({ tag: el.tagName, role: el.getAttribute('role'), text: (el.innerText||'').slice(0,200) });
    });
    out.bodyTextSample = (document.body.innerText || '').slice(0, 2000);
    return out;
}"""

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()
    for name, url in SURFACES:
        entry = {"name": name, "url": url, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        print(f"\n=== {name}: {url} ===")
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            entry["http_status"] = resp.status if resp else None
            page.wait_for_timeout(4000)
            entry["final_url"] = page.url
            snap = page.evaluate(SNAPSHOT_JS)
            entry["snapshot"] = snap
            print(f"  status={entry['http_status']} final={entry['final_url'][:90]}")
            print(f"  headings: {snap['headings'][:4]}")
            print(f"  buttons({len(snap['buttons'])}):")
            for b in snap["buttons"][:14]:
                print(f"    - text={b['text']!r} testid={b['dataTestid']} aria={b['aria']}")
            print(f"  inputs({len(snap['inputs'])}):")
            for i in snap["inputs"][:10]:
                print(f"    - {i['tag']} type={i['type']} name={i['name']} ph={i['placeholder']!r} testid={i['dataTestid']}")
            if snap["dialogs"]:
                print(f"  dialogs: {[d['text'][:80] for d in snap['dialogs']]}")
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"  ERROR: {entry['error']}")
        results.append(entry)
        with open(os.path.join(OUT, f"{name}_surface.json"), "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)
    browser.close()
print("\ncaptured ->", OUT)
