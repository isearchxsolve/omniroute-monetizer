"""Check live cookie state for the 4 wave-1 providers on CDP 9223 (T11-safe: names+lengths only)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

TARGETS = {
    "perplexity-web": ["perplexity.ai"],
    "t3-web": ["t3.chat"],
    "blackbox": ["blackbox.ai"],
    "muse-spark-web": ["meta.ai"],
}
STRONG = {
    "perplexity-web": ["__Secure-next-auth.session-token", "__Secure-perplexity_session"],
    "t3-web": ["session", "access-token", "sessionToken", "t3-session", "authjs.session-token", "wos-session"],
    "blackbox": ["token", "session", "auth", "jwt"],
    "muse-spark-web": ["c_user", "xs", "sessionid"],
}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=30000)
    ctx = browser.contexts[0]
    cookies = ctx.cookies()
    browser.close()

print(f"total cookies: {len(cookies)}")
for slug, doms in TARGETS.items():
    hits = [c for c in cookies if any((c.get('domain') or '').lstrip('.').lower() == d or (c.get('domain') or '').lstrip('.').lower().endswith('.'+d) for d in doms)]
    if not hits:
        print(f"\n{slug}: NO cookies")
        continue
    names = sorted({c['name'] for c in hits})
    strong_present = [n for n in STRONG.get(slug, []) if n in names]
    print(f"\n{slug}: {len(hits)} cookies")
    print(f"  strong auth present: {strong_present}")
    print(f"  all names: {names}")
