"""Query the live slim-Chrome CDP (port 9222) for decrypted cookies of the 14 targets.
CDP Network.getAllCookies returns plaintext values (v20 app-bound is decrypted by Chrome itself).
T11-safe: values never printed; candidates saved to gitignored state/generated_keys.json."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")

from playwright.sync_api import sync_playwright  # noqa: E402

TARGETS = {
    "adapta-web": ["adapta.one"],
    "blackbox-web": ["blackbox.ai"],
    "chatgpt-web": ["chatgpt.com", "openai.com"],
    "codebuddy-cn": ["copilot.tencent.com"],
    "grok-web": ["grok.com", "x.com", "twitter.com"],
    "microsoft-designer-web": ["officeapps.live.com", "live.com", "microsoft.com"],
    "muse-spark-web": ["meta.ai", "facebook.com"],
    "perplexity-web": ["perplexity.ai"],
    "suno": ["suno.ai", "suno.com"],
    "t3-web": ["t3.chat"],
    "udio": ["udio.com"],
    "veoaifree-web": ["veoaifree.com"],
    "yuanbao-web": ["yuanbao.tencent.com", "tencent.com"],
    "zed-hosted": ["zed.dev"],
}

# session-cookie names that matter per provider (auth-bearing)
AUTH_COOKIES = {
    "chatgpt-web": ["__Secure-next-auth.session-token"],
    "grok-web": ["auth_token", "ct0"],
    "zed-hosted": ["zed.session"],
    "perplexity-web": ["__Secure-perplexity_session"],
    "blackbox-web": ["session"],
}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=30000)
    ctx = browser.contexts[0]
    cookies = ctx.cookies()
    browser.close()

print(f"live CDP cookies: {len(cookies)}")
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

for slug in sorted(TARGETS):
    lst = hits.get(slug, [])
    if not lst:
        print(f"  {slug:26s} -- none")
        continue
    names = sorted({c["name"] for c in lst})
    print(f"  {slug:26s} {len(lst)} cookies: {names}")
    # build auth cookie value if the known auth cookie is present
    wanted = AUTH_COOKIES.get(slug, [])
    for w in wanted:
        # chunked support
        base = [c for c in lst if c["name"] == w]
        chunks = sorted([c for c in lst if c["name"].startswith(w + ".")],
                        key=lambda c: int(c["name"].rsplit(".", 1)[-1]) if c["name"].rsplit(".", 1)[-1].isdigit() else 0)
        if base:
            val = base[0]["value"]
            print(f"      -> auth cookie '{w}' present, len={len(val)}")
            store[f"browser_session:{slug}"] = {"value": val, "cookie": w, "harvested_at": "2026-08-18", "source": "cdp-live"}
        elif chunks:
            val = "".join(c["value"] for c in chunks)
            print(f"      -> auth cookie '{w}' chunked x{len(chunks)}, len={len(val)}")
            store[f"browser_session:{slug}"] = {"value": val, "cookie": w, "chunks": len(chunks), "harvested_at": "2026-08-18", "source": "cdp-live"}

if any(k.startswith("browser_session:") for k in store):
    json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)
    print("\nsaved candidate session(s) -> state/generated_keys.json (values masked)")
