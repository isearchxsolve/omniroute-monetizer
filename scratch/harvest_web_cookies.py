#!/usr/bin/env python3
"""Harvest browser-session cookies for chatgpt-web + gemini-web and inject
into OmniRoute as provider connections.

Flow (zero-fabrication, AGENTS.md rule 7):
  1. Attach to slim Chrome via CDP; extract ONLY the specific cookies:
       chatgpt-web : __Secure-next-auth.session-token @ chatgpt.com
       gemini-web  : __Secure-1PSID (+ __Secure-1PSIDTS) @ google.com
  2. Verify each cookie UPSTREAM with an authenticated request (200 OK +
     auth marker) BEFORE injecting. Report truthfully if inconclusive.
  3. Create (or update, idempotent) OmniRoute connection:
       POST /api/providers {provider, authType:"apikey", apiKey:<cookie>}
     (catalog authHeader=cookie means the cookie value goes in apiKey).
  4. Count LIVE only if OmniRoute test_connection returns valid=true.

T11-safe: cookie values are NEVER printed; only masked. Full values saved
to gitignored state/generated_keys.json.
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

import requests  # noqa: E402
from omniroute_api import OmniRouteAPI, mask_token  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0 Safari/537.36")

TARGETS = {
    "chatgpt-web": {
        "name": "ChatGPT Web (Plus/Pro)",
        "cookies": [("chatgpt.com", "__Secure-next-auth.session-token")],
        "join": None,  # single cookie value
    },
    "gemini-web": {
        "name": "Gemini Web (Free)",
        "cookies": [("google.com", "__Secure-1PSID"),
                    ("google.com", "__Secure-1PSIDTS")],
        "join": ";",  # authHint: 1PSID optionally + 1PSIDTS separated by semicolon
    },
}


def extract_cookies() -> dict:
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=30000)
        ctx = browser.contexts[0]
        cookies = ctx.cookies()
        browser.close()
    for slug, spec in TARGETS.items():
        vals = []
        for dom, name in spec["cookies"]:
            hit = None
            for c in cookies:
                cd = (c.get("domain") or "").lstrip(".").lower()
                if c.get("name") == name and (cd == dom or cd.endswith("." + dom) or dom.endswith(cd)):
                    hit = c.get("value")
                    break
            if hit:
                vals.append(hit)
        if vals:
            out[slug] = spec["join"].join(vals) if spec["join"] else vals[0]
    return out


def verify_chatgpt(cookie: str) -> dict:
    """GET chatgpt.com/backend-api/models with the session cookie."""
    try:
        r = requests.get(
            "https://chatgpt.com/backend-api/models",
            headers={"User-Agent": UA, "Accept": "application/json",
                     "Cookie": f"__Secure-next-auth.session-token={cookie}"},
            timeout=30, allow_redirects=True)
        ok = r.status_code == 200
        models = 0
        if ok:
            try:
                models = len(r.json().get("models", []))
            except Exception:
                ok = False
        return {"verified": ok and models > 0, "status": r.status_code,
                "detail": f"{models} models listed" if ok else r.text[:120]}
    except Exception as e:
        return {"verified": False, "status": None,
                "detail": f"{type(e).__name__}: {str(e)[:120]}"}


def verify_gemini(cookie: str) -> dict:
    """Soft upstream check: GET gemini.google.com/app with the 1PSID cookie.
    Authenticated if no redirect to accounts.google.com and page has app data."""
    try:
        r = requests.get(
            "https://gemini.google.com/app",
            headers={"User-Agent": UA, "Accept": "text/html", "Cookie": cookie},
            timeout=30, allow_redirects=True)
        final = r.url
        body = r.text
        redirected_to_login = "accounts.google.com" in final
        auth_markers = any(m in body for m in (
            "WIZ_global_data", "AF_initDataCallback", "gemini", "user"))
        verified = (r.status_code == 200 and not redirected_to_login
                    and auth_markers)
        return {"verified": verified, "status": r.status_code,
                "detail": (f"final_url={final[:60]} login_redirect="
                           f"{redirected_to_login} markers={auth_markers}")}
    except Exception as e:
        return {"verified": False, "status": None,
                "detail": f"{type(e).__name__}: {str(e)[:120]}"}


def main() -> int:
    print("[1] extracting cookies from Chrome profile via CDP...")
    cookies = extract_cookies()
    for slug in TARGETS:
        v = cookies.get(slug)
        print(f"    {slug:14s} cookie={'FOUND ' + mask_token(v) if v else 'MISSING'}")

    if not cookies:
        print("[-] no harvestable cookies found")
        return 1

    # save full values (gitignored)
    keys = {}
    if os.path.exists(KEYS_PATH):
        try:
            keys = json.load(open(KEYS_PATH, encoding="utf-8"))
        except Exception:
            keys = {}
    for slug, v in cookies.items():
        keys[f"{slug}_cookie"] = {"value": v, "harvested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                  "source": "chrome_profile_cdp"}
    json.dump(keys, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)

    print("\n[2] upstream verification (before injection)...")
    verified = {}
    if "chatgpt-web" in cookies:
        verified["chatgpt-web"] = verify_chatgpt(cookies["chatgpt-web"])
        v = verified["chatgpt-web"]
        print(f"    chatgpt-web  verified={v['verified']} status={v['status']} {v['detail']}")
    if "gemini-web" in cookies:
        verified["gemini-web"] = verify_gemini(cookies["gemini-web"])
        v = verified["gemini-web"]
        print(f"    gemini-web   verified={v['verified']} status={v['status']} {v['detail']}")

    print("\n[3] OmniRoute injection...")
    pw = resolve_password()
    if not pw:
        print("[-] no OmniRoute management password resolvable")
        return 3
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return 3
    conns = api.get_connections()
    existing = {c.get("provider"): c for c in conns}

    results = {}
    for slug, cookie in cookies.items():
        spec = TARGETS[slug]
        upv = verified.get(slug, {})
        if not upv.get("verified"):
            print(f"    {slug}: upstream NOT verified -> still injecting? "
                  f"OmniRoute test will decide (honest reporting)")
        ex = existing.get(slug)
        if ex:
            cid = ex["id"]
            res = api.update_connection(cid, {"apiKey": cookie, "isActive": True})
            print(f"    {slug}: updated existing conn {cid} -> HTTP {res.get('http_status')}")
        else:
            payload = {"provider": slug, "name": spec["name"],
                       "authType": "apikey", "apiKey": cookie, "isActive": True}
            r = api.session.post(f"{api.api}/providers", json=payload, timeout=20)
            print(f"    {slug}: POST /api/providers -> HTTP {r.status_code}")
            if r.status_code not in (200, 201):
                print(f"        create failed: {r.text[:250]}")
                results[slug] = {"live": False, "reason": f"create HTTP {r.status_code}"}
                continue
            body = r.json()
            cid = body.get("id") or (body.get("connection") or {}).get("id")
            if not cid:
                print(f"        no id in response: {json.dumps(body)[:250]}")
                results[slug] = {"live": False, "reason": "no connection id"}
                continue
            print(f"        created connection {cid}")

        # sync models then test
        rs = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
        print(f"        sync-models -> HTTP {rs.status_code}")
        test = api.test_connection(cid)
        http = test.get("http_status")
        res = test.get("result") or {}
        ok = bool(http == 200 and isinstance(res, dict) and (
            res.get("valid") or res.get("success") or res.get("ok") or res.get("healthy")))
        print(f"        test_connection -> HTTP {http} valid={ok} "
              f"detail={json.dumps(res)[:250]}")
        results[slug] = {"live": ok, "conn_id": cid,
                         "upstream_verified": bool(upv.get("verified")),
                         "upstream_detail": upv.get("detail", "")}

    print("\n=== RESULT ===")
    for slug, r in results.items():
        print(f"  {slug:14s} live={r.get('live')} upstream_verified={r.get('upstream_verified')}")
    json.dump({"harvested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "results": results},
              open(os.path.join(ROOT, "state", "web_cookie_harvest.json"), "w",
                   encoding="utf-8"), indent=2)
    return 0 if any(r.get("live") for r in results.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
