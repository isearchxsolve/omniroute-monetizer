#!/usr/bin/env python3
"""Cookie detection for the 15 NEEDS_BROWSER providers.

Attaches to the slim Chrome profile via CDP (:9222), exports the current
cookie jar, and reports which of the 15 browser-session provider domains
already have session cookies (= user is logged in = harvestable).

Shallow-first: no navigation, no clicks — pure cookie inspection.
T11-safe: cookie VALUES are never printed, only names/counts.
Output: state/browser_session_cookie_check.json
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "state", "browser_session_cookie_check.json")

# provider slug -> list of domain substrings that indicate a session
TARGETS = {
    "adapta-web": ["adapta.one"],
    "blackbox-web": ["blackbox.ai"],
    "chatgpt-web": ["chatgpt.com", "openai.com", "auth.openai.com"],
    "codebuddy-cn": ["tencent.com", "copilot.tencent.com"],
    "gemini-web": ["gemini.google.com", "google.com"],
    "grok-web": ["grok.com", "x.com"],
    "microsoft-designer-web": ["officeapps.live.com", "live.com", "microsoft.com"],
    "muse-spark-web": ["meta.ai", "meta.com", "facebook.com"],
    "perplexity-web": ["perplexity.ai"],
    "suno": ["suno.ai", "suno.com"],
    "t3-web": ["t3.chat"],
    "udio": ["udio.com"],
    "veoaifree-web": ["veoaifree.com"],
    "yuanbao-web": ["yuanbao.tencent.com", "tencent.com"],
    "zed-hosted": ["zed.dev"],
}

# session-indicating cookie name patterns (case-insensitive substrings)
SESSION_HINTS = ("session", "token", "auth", "access", "sid", "jwt", "login",
                 "user", "account", "__secure-", "sso", "cookie", "id")


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=30000)
        except Exception as e:
            print(f"CDP attach FAILED: {type(e).__name__}: {str(e)[:150]}")
            print("-> run scratch/ensure_cdp.py first to launch slim Chrome")
            return 1
        ctx = browser.contexts[0]
        cookies = ctx.cookies()
        browser.close()

    print(f"attached to CDP; {len(cookies)} cookies total\n")

    # index cookies by domain
    by_domain = {}
    for c in cookies:
        d = (c.get("domain") or "").lstrip(".").lower()
        by_domain.setdefault(d, []).append(c.get("name", "?"))

    results = {}
    have_session = []
    have_any = []
    none = []

    for slug, doms in TARGETS.items():
        matched = {}
        for d, names in by_domain.items():
            if any(t in d for t in doms):
                matched[d] = names
        session_cookies = []
        for d, names in matched.items():
            for n in names:
                if any(h in n.lower() for h in SESSION_HINTS):
                    session_cookies.append(f"{d}:{n}")
        total = sum(len(n) for n in matched.values())
        verdict = ("HAS_SESSION" if session_cookies
                   else "HAS_COOKIES" if total else "NO_COOKIES")
        results[slug] = {
            "verdict": verdict,
            "domains_matched": {d: len(n) for d, n in matched.items()},
            "total_cookies": total,
            "session_cookie_names": sorted(set(session_cookies))[:12],
        }
        if session_cookies:
            have_session.append(slug)
        elif total:
            have_any.append(slug)
        else:
            none.append(slug)
        print(f"  {slug:24s} {verdict:12s} cookies={total:3d} "
              f"session={len(session_cookies)}")

    print(f"\n=== SUMMARY ===")
    print(f"  HAS_SESSION (harvestable now): {len(have_session)}  {have_session}")
    print(f"  HAS_COOKIES (no obvious session cookie): {len(have_any)}  {have_any}")
    print(f"  NO_COOKIES (not logged in): {len(none)}  {none}")

    json.dump({"checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "total_cookies": len(cookies),
               "results": results,
               "have_session": have_session,
               "have_any": have_any,
               "none": none},
              open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
