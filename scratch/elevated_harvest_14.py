"""ELEVATED-ONLY harvest: extract v20 app-bound session cookies for chatgpt-web,
grok-web, zed-hosted from REAL Chrome via rookiepy, verify upstream, inject into OmniRoute.

MUST be run from an ELEVATED PowerShell (rookiepy requires admin for Chrome v130+
app-bound encryption).

T11-safe: cookie values NEVER printed; stored only in gitignored state/generated_keys.json.
Results (no secrets) -> state/harvest_14_results.json
"""
import ctypes
import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")
RESULTS_PATH = os.path.join(ROOT, "state", "harvest_14_results.json")
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0 Safari/537.36")

# 0. elevation check
if not ctypes.windll.shell32.IsUserAnAdmin():
    print("ERROR: this script must run ELEVATED (app-bound cookie decryption needs admin).")
    print("Run from an elevated PowerShell: .\\.venv\\Scripts\\python.exe scratch\\elevated_harvest_14.py")
    sys.exit(2)

import requests  # noqa: E402

# Prefer the maintained fork (rookie-cookies) which supports Chrome v20 App-Bound
# encryption on Windows; fall back to the archived rookiepy.
try:
    import rookie_cookies as _rc
    _BACKEND = "rookie-cookies"
except ImportError:
    _rc = None
try:
    import rookiepy as _rp
except ImportError:
    _rp = None
if _rc is None and _rp is None:
    print("ERROR: neither rookie-cookies nor rookiepy is installed.")
    sys.exit(3)
if _rc is None:
    _BACKEND = "rookiepy"

TARGETS = {
    "chatgpt-web": {
        "domains": ["chatgpt.com", "openai.com"],
        "auth_cookies": ["__Secure-next-auth.session-token"],
    },
    "grok-web": {
        "domains": ["grok.com", "x.com", "twitter.com"],
        "auth_cookies": ["auth_token", "ct0"],
    },
    "zed-hosted": {
        "domains": ["zed.dev"],
        "auth_cookies": ["zed.session"],
    },
}


def verify_chatgpt(value: str) -> dict:
    try:
        r = requests.get("https://chatgpt.com/backend-api/models",
                         headers={"User-Agent": UA, "Accept": "application/json",
                                  "Cookie": f"__Secure-next-auth.session-token={value}"},
                         timeout=30, allow_redirects=True)
        ok = r.status_code == 200
        n = 0
        if ok:
            try:
                n = len(r.json().get("models", []))
            except Exception:
                ok = False
        return {"verified": ok and n > 0, "status": r.status_code,
                "detail": f"{n} models listed" if ok else r.text[:150]}
    except Exception as e:
        return {"verified": False, "status": None, "detail": f"{type(e).__name__}: {str(e)[:150]}"}


def verify_grok(cookies: dict) -> dict:
    """grok.com SSOs off x.com auth_token. Try grok user-info then x.com verify."""
    jar = "; ".join(f"{k}={v}" for k, v in cookies.items())
    attempts = []
    for url in ("https://grok.com/rest/app-chat/user/info",
                "https://x.com/i/api/1.1/account/verify_credentials.json"):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Cookie": jar,
                                           "Accept": "application/json"},
                             timeout=30, allow_redirects=False)
            attempts.append(f"{url.split('/')[2]}:{r.status_code}")
            if r.status_code == 200:
                return {"verified": True, "status": 200, "detail": " | ".join(attempts)}
        except Exception as e:
            attempts.append(f"{url.split('/')[2]}:{type(e).__name__}")
    return {"verified": False, "status": None, "detail": " | ".join(attempts)}


def verify_zed(value: str) -> dict:
    try:
        r = requests.get("https://zed.dev/api/user",
                         headers={"User-Agent": UA, "Cookie": f"zed.session={value}",
                                  "Accept": "application/json"},
                         timeout=30, allow_redirects=False)
        ok = r.status_code == 200
        return {"verified": ok, "status": r.status_code,
                "detail": (r.text[:150] if not ok else "user info 200")}
    except Exception as e:
        return {"verified": False, "status": None, "detail": f"{type(e).__name__}: {str(e)[:150]}"}


def main() -> int:
    results = {"ts": datetime.now(timezone.utc).isoformat(), "targets": {}}

    # 1. extract
    all_domains = sorted({d for t in TARGETS.values() for d in t["domains"]})
    print(f"extracting cookies for: {all_domains} (backend={_BACKEND})")
    try:
        if _BACKEND == "rookie-cookies":
            cookies = _rc.chrome(all_domains)
        else:
            cookies = _rp.chrome(domains=all_domains)
    except Exception as e:
        print(f"{_BACKEND} FAILED:", type(e).__name__, str(e)[:300])
        return 1
    print(f"got {len(cookies)} cookies total")

    extracted = {}
    for slug, spec in TARGETS.items():
        lst = [c for c in cookies
               if any((c.get("domain") or "").lstrip(".").lower() == d
                      or (c.get("domain") or "").lstrip(".").lower().endswith("." + d)
                      for d in spec["domains"])]
        names = sorted({c["name"] for c in lst})
        print(f"  {slug}: {len(lst)} cookies {names[:12]}")
        got = {}
        for w in spec["auth_cookies"]:
            base = [c for c in lst if c["name"] == w]
            chunks = sorted([c for c in lst if c["name"].startswith(w + ".")],
                            key=lambda c: int(c["name"].rsplit(".", 1)[-1])
                            if c["name"].rsplit(".", 1)[-1].isdigit() else 0)
            if base:
                got[w] = base[0]["value"]
            elif chunks:
                got[w] = "".join(c["value"] for c in chunks)
        if got:
            extracted[slug] = got
            print(f"    -> auth cookie(s) extracted: {list(got)} (values masked)")
        else:
            print("    -> NO auth cookie present")

    # 2. verify upstream
    verifications = {}
    if "chatgpt-web" in extracted:
        verifications["chatgpt-web"] = verify_chatgpt(extracted["chatgpt-web"]["__Secure-next-auth.session-token"])
    if "grok-web" in extracted:
        verifications["grok-web"] = verify_grok(extracted["grok-web"])
    if "zed-hosted" in extracted:
        verifications["zed-hosted"] = verify_zed(extracted["zed-hosted"]["zed.session"])
    for slug, v in verifications.items():
        print(f"  verify {slug}: verified={v['verified']} status={v['status']} detail={v['detail'][:100]}")

    # 3. save extracted values (gitignored)
    store = {}
    if os.path.exists(KEYS_PATH):
        try:
            store = json.loads(open(KEYS_PATH, encoding="utf-8").read())
        except Exception:
            store = {}
    for slug, got in extracted.items():
        primary = got.get("__Secure-next-auth.session-token") or got.get("auth_token") or got.get("zed.session")
        store[f"browser_session:{slug}"] = {
            "value": primary, "all": got,
            "harvested_at": "2026-08-18", "source": f"{_BACKEND}-elevated",
            "upstream_verified": verifications.get(slug, {}).get("verified", False),
        }
    json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)

    # 4. inject ONLY upstream-verified into OmniRoute
    injected = {}
    verified_slugs = [s for s, v in verifications.items() if v.get("verified")]
    if verified_slugs:
        from omniroute_api import OmniRouteAPI
        api = OmniRouteAPI()
        api.login()
        r = api.session.get(f"{api.api}/providers", timeout=60)
        conns = r.json().get("connections", [])
        for slug in verified_slugs:
            primary = (extracted[slug].get("__Secure-next-auth.session-token")
                       or extracted[slug].get("auth_token")
                       or extracted[slug].get("zed.session"))
            existing = next((c for c in conns if c.get("provider") == slug), None)
            payload = {"provider": slug, "authType": "apikey", "apiKey": primary,
                       "name": slug, "isActive": True}
            if existing:
                rr = api.session.put(f"{api.api}/providers/{existing['id']}",
                                     json={**existing, "apiKey": primary, "isActive": True},
                                     timeout=120)
            else:
                rr = api.session.post(f"{api.api}/providers", json=payload, timeout=120)
            injected[slug] = {"http": rr.status_code, "body": rr.text[:200]}
            print(f"  inject {slug}: HTTP {rr.status_code} {rr.text[:120]}")

    # 5. results file (no secrets)
    for slug in TARGETS:
        results["targets"][slug] = {
            "extracted": slug in extracted,
            "verification": verifications.get(slug),
            "injection": injected.get(slug),
        }
    json.dump(results, open(RESULTS_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nresults -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
