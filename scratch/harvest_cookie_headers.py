"""Harvest full Cookie headers for signed-in wave-1 providers (CDP 9223).

Builds the exact Cookie header string each OmniRoute executor expects:
  - perplexity-web : full Cookie header (perplexity.ai) -> apiKey
  - t3-web         : full Cookie header (t3.chat, MUST include convex-session-id) -> apiKey

T11-safe: cookie VALUES are never printed; only names + lengths. Full headers
saved to gitignored state/generated_keys.json.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")
PORT = 9223

from playwright.sync_api import sync_playwright  # noqa: E402

# slug -> (auth domains, required cookie names that MUST be present)
TARGETS = {
    "perplexity-web": {
        "domains": ["perplexity.ai"],
        "required": ["__Secure-next-auth.session-token"],
    },
    "t3-web": {
        "domains": ["t3.chat"],
        "required": ["convex-session-id"],
    },
}


def build_cookie_header(cookies, domains):
    """Join all cookies for the domain set into a 'name=value; name=value' header."""
    parts = []
    for c in cookies:
        dom = (c.get("domain") or "").lstrip(".").lower()
        if any(dom == d or dom.endswith("." + d) for d in domains):
            parts.append(f"{c['name']}={c['value']}")
    return "; ".join(parts)


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]
    cookies = ctx.cookies()
    browser.close()

store = {}
if os.path.exists(KEYS_PATH):
    try:
        store = json.loads(open(KEYS_PATH, encoding="utf-8").read())
    except Exception:
        store = {}

results = {}
for slug, spec in TARGETS.items():
    header = build_cookie_header(cookies, spec["domains"])
    names = sorted({c["name"] for c in cookies
                    if any((c.get("domain") or "").lstrip(".").lower() == d
                           or (c.get("domain") or "").lstrip(".").lower().endswith("." + d)
                           for d in spec["domains"])})
    missing = [r for r in spec["required"] if r not in names]
    ok = not missing and len(header) > 0
    results[slug] = {"ok": ok, "missing": missing, "n_cookies": len(names), "header_len": len(header)}
    print(f"{slug}: {'OK' if ok else 'MISSING ' + str(missing)} "
          f"cookies={len(names)} header_len={len(header)}")
    print(f"  names: {names}")
    if ok:
        store[f"cookie_header:{slug}"] = {
            "cookie_header": header,
            "cookie_names": names,
            "harvested_at": "2026-08-18",
            "source": "pure-chrome-cdp-9223",
            "note": "autonomous Google SSO login (blueprint #122)",
        }

json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)
print("\nsaved cookie headers ->", [k for k in store if k.startswith("cookie_header:")])
print(json.dumps(results, indent=2))
