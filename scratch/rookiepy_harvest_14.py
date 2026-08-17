"""Use rookiepy to extract session cookies for the 14 NEEDS_BROWSER targets from REAL Chrome.
rookiepy handles v20 app-bound cookies via Chrome's elevation COM interface.
T11-safe: values never printed; saved to gitignored state/generated_keys.json."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")

import rookiepy  # noqa: E402

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

AUTH_COOKIES = {
    "chatgpt-web": ["__Secure-next-auth.session-token"],
    "grok-web": ["auth_token", "ct0"],
    "zed-hosted": ["zed.session"],
}

all_domains = sorted({d for ds in TARGETS.values() for d in ds})
print("querying rookiepy.chrome for:", all_domains)
try:
    cookies = rookiepy.chrome(domains=all_domains)
except Exception as e:
    print("rookiepy.chrome failed:", type(e).__name__, str(e)[:300])
    sys.exit(1)

print(f"got {len(cookies)} cookies")

hits = {}
for c in cookies:
    dom = (c.get("domain") or "").lstrip(".").lower()
    for slug, doms in TARGETS.items():
        for d in doms:
            if dom == d or dom.endswith("." + d):
                hits.setdefault(slug, []).append(c)
                break

store = {}
if os.path.exists(KEYS_PATH):
    try:
        store = json.loads(open(KEYS_PATH, encoding="utf-8").read())
    except Exception:
        store = {}

print("\n=== hits per target ===")
for slug in sorted(TARGETS):
    lst = hits.get(slug, [])
    if not lst:
        print(f"  {slug:26s} -- none")
        continue
    names = sorted({c["name"] for c in lst})
    print(f"  {slug:26s} {len(lst)} cookies: {names}")
    for w in AUTH_COOKIES.get(slug, []):
        base = [c for c in lst if c["name"] == w]
        chunks = sorted([c for c in lst if c["name"].startswith(w + ".")],
                        key=lambda c: int(c["name"].rsplit(".", 1)[-1]) if c["name"].rsplit(".", 1)[-1].isdigit() else 0)
        if base:
            val = base[0]["value"]
            print(f"      -> '{w}' present, len={len(val)}")
            store[f"browser_session:{slug}"] = {"value": val, "cookie": w, "harvested_at": "2026-08-18", "source": "rookiepy"}
        elif chunks:
            val = "".join(c["value"] for c in chunks)
            print(f"      -> '{w}' chunked x{len(chunks)}, len={len(val)}")
            store[f"browser_session:{slug}"] = {"value": val, "cookie": w, "chunks": len(chunks), "harvested_at": "2026-08-18", "source": "rookiepy"}

if any(k.startswith("browser_session:") for k in store):
    json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)
    print("\nsaved -> state/generated_keys.json (values masked)")
else:
    print("\nno auth cookies extracted")
