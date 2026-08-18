"""Harvest sessions from the PURE Chrome profile (CDP port 9223) after the user
completes Google SSO signups (gate relaxation #120).

T11-safe: cookie values are NEVER printed; candidates saved to gitignored
state/generated_keys.json. Reports only cookie NAMES + lengths per target.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")
PORT = 9223

from playwright.sync_api import sync_playwright  # noqa: E402

# Wave-1 Google-SSO candidates and their auth-bearing domains.
TARGETS = {
    "perplexity-web": ["perplexity.ai"],
    "t3-web": ["t3.chat"],
    "blackbox": ["blackbox.ai"],
    "muse-spark-web": ["meta.ai"],
}

# Known auth cookie names where established (extend as discovered).
AUTH_COOKIES = {
    "perplexity-web": ["__Secure-perplexity_session"],
}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]
    cookies = ctx.cookies()
    browser.close()

print(f"live CDP cookies (port {PORT}): {len(cookies)}")
domains = sorted({(c.get("domain") or "").lstrip(".") for c in cookies})
print("domains:", domains)

hits = {}
for c in cookies:
    dom = (c.get("domain") or "").lstrip(".").lower()
    for slug, doms in TARGETS.items():
        for d in doms:
            if dom == d or dom.endswith("." + d):
                hits.setdefault(slug, []).append(c)
                break

print("\n=== hits per target ===")
store = {}
if os.path.exists(KEYS_PATH):
    try:
        store = json.loads(open(KEYS_PATH, encoding="utf-8").read())
    except Exception:
        store = {}

found = []
for slug in sorted(TARGETS):
    lst = hits.get(slug, [])
    if not lst:
        print(f"  {slug:20s} -- none (not signed in yet?)")
        continue
    names = sorted({c["name"] for c in lst})
    print(f"  {slug:20s} {len(lst)} cookies: {names}")
    found.append(slug)
    # Save ALL cookies for the domain set (OmniRoute web providers take full cookie jars).
    jar = {c["name"]: c["value"] for c in lst}
    store[f"browser_session:{slug}"] = {
        "cookies": jar,
        "cookie_names": names,
        "harvested_at": "2026-08-18",
        "source": "pure-chrome-cdp-9223",
        "note": "user-driven Google SSO (gate relaxation #120)",
    }
    wanted = AUTH_COOKIES.get(slug, [])
    for w in wanted:
        if w in jar:
            print(f"      -> known auth cookie '{w}' present, len={len(jar[w])}")

if found:
    json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nsaved session(s) for: {found} -> state/generated_keys.json (values masked in terminal)")
    print("NEXT: inject into OmniRoute + e2e /v1 verify (zero-fabrication: LIVE only on real completion proof).")
else:
    print("\nNo target sessions found yet. Complete Google SSO in the tabs, then re-run.")
