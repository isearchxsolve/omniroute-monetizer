#!/usr/bin/env python3
"""Tier B read-only DOM recon: navigate 3 provider dashboards with the persistent
browser profile, detect auth walls, dump DOM structure (buttons/inputs/key elements).
NO clicks, NO form fills, NO key creation. Output: state/dom_recon/*.json + summary."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROFILE = os.path.join(ROOT, "state", "browser_profile")
OUT = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(OUT, exist_ok=True)

TARGETS = [
    {
        "name": "openrouter",
        "url": "https://openrouter.ai/keys",
        "login_markers": ["sign in", "sign-in", "log in", "continue with", "clerk"],
        "authed_markers": ["create key", "api key", "provisioning"],
    },
    {
        "name": "anthropic",
        "url": "https://console.anthropic.com/settings/keys",
        "login_markers": ["sign in", "log in", "continue with", "workos"],
        "authed_markers": ["create key", "api keys"],
    },
    {
        "name": "github",
        "url": "https://github.com/settings/tokens",
        "login_markers": ["sign in to github", "username or email"],
        "authed_markers": ["personal access tokens", "generate new token"],
    },
]


def snapshot_page(page):
    """Extract interactive elements + text skeleton without clicking anything."""
    return page.evaluate(
        """() => {
        const out = { title: document.title, url: location.href, buttons: [], inputs: [], links: [], headings: [] };
        const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(el => {
            if (!vis(el)) return;
            out.buttons.push({
                text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                id: el.id || null,
                classes: (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0,3).join(' ') : '',
                aria: el.getAttribute('aria-label') || null,
            });
        });
        document.querySelectorAll('input, textarea, select').forEach(el => {
            if (!vis(el)) return;
            out.inputs.push({
                tag: el.tagName.toLowerCase(), type: el.type || null, name: el.name || null,
                id: el.id || null, placeholder: el.placeholder || null,
                aria: el.getAttribute('aria-label') || null,
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
        out.bodyTextSample = (document.body.innerText || '').slice(0, 1500);
        return out;
    }"""
    )


def main():
    results = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for t in TARGETS:
            entry = {"name": t["name"], "url": t["url"], "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            print(f"\n=== {t['name']}: {t['url']} ===")
            try:
                resp = page.goto(t["url"], wait_until="domcontentloaded", timeout=30000)
                entry["http_status"] = resp.status if resp else None
                page.wait_for_timeout(3500)  # let SPA hydrate
                entry["final_url"] = page.url
                snap = snapshot_page(page)
                entry["snapshot"] = snap
                body = (snap.get("bodyTextSample") or "").lower()
                title = (snap.get("title") or "").lower()
                hay = body + " " + title
                login_hit = [m for m in t["login_markers"] if m in hay]
                authed_hit = [m for m in t["authed_markers"] if m in hay]
                if authed_hit and not login_hit:
                    verdict = "AUTHENTICATED"
                elif login_hit and not authed_hit:
                    verdict = "AUTH_WALL"
                elif authed_hit and login_hit:
                    verdict = "AMBIGUOUS"
                else:
                    verdict = "UNKNOWN"
                entry["verdict"] = verdict
                entry["login_markers_hit"] = login_hit
                entry["authed_markers_hit"] = authed_hit
                print(f"  status={entry['http_status']} final_url={entry['final_url']}")
                print(f"  verdict={verdict} login_hits={login_hit} authed_hits={authed_hit}")
                print(f"  buttons({len(snap['buttons'])}): {[b['text'][:40] for b in snap['buttons'][:8]]}")
                print(f"  headings: {snap['headings'][:5]}")
            except Exception as e:
                entry["verdict"] = "ERROR"
                entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                print(f"  ERROR: {entry['error']}")
            results.append(entry)
            with open(os.path.join(OUT, f"{t['name']}_recon.json"), "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2, ensure_ascii=False)
        ctx.close()

    with open(os.path.join(OUT, "recon_summary.json"), "w", encoding="utf-8") as f:
        json.dump(
            [{"name": r["name"], "verdict": r.get("verdict"), "http_status": r.get("http_status"),
              "final_url": r.get("final_url"), "error": r.get("error")} for r in results],
            f, indent=2,
        )
    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['name']}: {r.get('verdict')}")


if __name__ == "__main__":
    main()
