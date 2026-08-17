"""ELEVATED-ONLY harvest v2: ALL Chrome profiles, OmniRoute-matching credential
formats and verification endpoints.

Corrections vs v1 (from OmniRoute source inspection):
- chatgpt-web: verify via GET https://chatgpt.com/api/auth/session (needs
  accessToken in JSON) — NOT /backend-api/models (that needs a Bearer token).
  Inject the bare reassembled __Secure-next-auth.session-token value.
- grok-web: needs grok.com `sso` + `sso-rw` cookies (buildGrokCookieHeader),
  NOT x.com auth_token. Inject the cookie line "sso=...; sso-rw=...".
- zed-hosted: OAuth provider in OmniRoute (native-app RSA sign-in), NOT
  cookie-based — skipped and reclassified.
- Scans ALL Chrome profiles via chromium_based(key_path, db_path) per profile.

MUST be run from an ELEVATED PowerShell (v20 app-bound decryption needs admin).
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

UA_FF = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15; rv:152.0) "
         "Gecko/20100101 Firefox/152.0")  # OmniRoute's chatgpt validator UA
UA_CHROME = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36')

if not ctypes.windll.shell32.IsUserAnAdmin():
    print("ERROR: this script must run ELEVATED (app-bound cookie decryption needs admin).")
    print("Run from an elevated PowerShell: .\\.venv\\Scripts\\python.exe scratch\\elevated_harvest_14.py")
    sys.exit(2)

import requests  # noqa: E402
import rookie_cookies as rc  # noqa: E402

CHATGPT_DOMAINS = ["chatgpt.com", "openai.com"]
GROK_DOMAINS = ["grok.com"]


def extract_all_profiles(domains):
    """Return {display_name: [cookie dicts]} for every Chrome profile."""
    out = {}
    try:
        profs = rc.chrome_profiles()
    except Exception as e:
        print("chrome_profiles FAILED:", type(e).__name__, str(e)[:300])
        return out
    key_path = os.path.join(os.environ["LOCALAPPDATA"],
                            "Google", "Chrome", "User Data", "Local State")
    for p in profs:
        prof = p.get("profile", {})
        name = prof.get("display_name") or prof.get("profile_id", "?")[:12]
        srcs = [s for s in p.get("sources", []) if s.get("format") == "chromium_sqlite"]
        if not srcs:
            print(f"  profile {name}: no chromium_sqlite source, skip")
            continue
        db_path = srcs[0]["path"]
        try:
            cookies = rc.chromium_based(key_path=key_path, db_path=db_path, domains=domains)
            out[name] = cookies
            print(f"  profile {name}: {len(cookies)} cookies")
        except Exception as e:
            print(f"  profile {name}: extract FAILED {type(e).__name__}: {str(e)[:200]}")
            out[name] = []
    return out


def reassemble_chunked(cookies, base_name):
    """Reassemble name.0/name.1/... chunks; fall back to exact-name cookie."""
    exact = [c for c in cookies if c["name"] == base_name]
    if exact:
        return exact[0]["value"]
    chunks = [c for c in cookies if c["name"].startswith(base_name + ".")
              and c["name"].rsplit(".", 1)[-1].isdigit()]
    if not chunks:
        return None
    chunks.sort(key=lambda c: int(c["name"].rsplit(".", 1)[-1]))
    return "".join(c["value"] for c in chunks)


def verify_chatgpt(token):
    """OmniRoute's actual validation: GET /api/auth/session, need accessToken."""
    try:
        r = requests.get(
            "https://chatgpt.com/api/auth/session",
            headers={
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Cookie": f"__Secure-next-auth.session-token={token}",
                "Origin": "https://chatgpt.com",
                "Pragma": "no-cache",
                "Referer": "https://chatgpt.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": UA_FF,
            },
            timeout=30, allow_redirects=True)
        cf_mitigated = r.headers.get("cf-mitigated")
        ctype = r.headers.get("content-type", "")
        has_access_token = False
        if r.status_code == 200 and "json" in ctype:
            try:
                has_access_token = bool(r.json().get("accessToken"))
            except Exception:
                pass
        return {
            "verified": has_access_token,
            "status": r.status_code,
            "cf_mitigated": cf_mitigated,
            "detail": ("accessToken present" if has_access_token
                       else f"ctype={ctype[:40]} body={r.text[:80]!r}"),
        }
    except Exception as e:
        return {"verified": False, "status": None, "cf_mitigated": None,
                "detail": f"{type(e).__name__}: {str(e)[:150]}"}


def verify_grok(cookie_line):
    """Best-effort from Python (OmniRoute uses a TLS-impersonating client;
    plain requests may hit the anti-bot wall — OmniRoute's own validator is
    authoritative after injection)."""
    try:
        r = requests.post(
            "https://grok.com/rest/app-chat/conversations/new",
            headers={
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "Cookie": cookie_line,
                "Origin": "https://grok.com",
                "Referer": "https://grok.com/",
                "User-Agent": UA_CHROME,
            },
            json={"temporary": True, "modeId": "fast", "message": "test"},
            timeout=30, allow_redirects=False)
        body = r.text[:120]
        anti_bot = "anti-bot" in body or "cf-chl" in body or r.status_code == 403
        return {
            "verified": r.status_code == 200,
            "status": r.status_code,
            "anti_bot_wall": anti_bot,
            "detail": body.replace("\n", " "),
        }
    except Exception as e:
        return {"verified": False, "status": None, "anti_bot_wall": None,
                "detail": f"{type(e).__name__}: {str(e)[:150]}"}


def main():
    results = {"ts": datetime.now(timezone.utc).isoformat(),
               "backend": f"rookie-cookies {rc.version()}",
               "chatgpt_candidates": {}, "grok_candidates": {},
               "zed_hosted": "RECLASSIFIED_OAUTH_PROVIDER (not cookie-based)",
               "verifications": {}, "injections": {}}

    # ---- 1. extract from ALL profiles ----
    print("== chatgpt/openai domains ==")
    cgpt_by_profile = extract_all_profiles(CHATGPT_DOMAINS)
    print("== grok.com domains ==")
    grok_by_profile = extract_all_profiles(GROK_DOMAINS)

    # ---- 2. build candidates ----
    cgpt_candidates = []  # (profile, token, extra_cookie_names)
    for prof, cookies in cgpt_by_profile.items():
        token = reassemble_chunked(cookies, "__Secure-next-auth.session-token")
        if token:
            extras = sorted(c["name"] for c in cookies
                            if c["name"] in ("__cf_bm", "cf_clearance", "_cfuvid",
                                             "__Secure-oai-is", "__oailb"))
            cgpt_candidates.append((prof, token, extras))
            results["chatgpt_candidates"][prof] = {
                "token_len": len(token), "extras": extras}
            print(f"  chatgpt candidate from profile {prof!r}: token len={len(token)} extras={extras}")

    grok_lines = {}  # profile -> cookie line
    for prof, cookies in grok_by_profile.items():
        sso = reassemble_chunked(cookies, "sso")
        if sso:
            parts = [f"sso={sso}"]
            for extra in ("sso-rw", "cf_clearance", "__cf_bm"):
                v = reassemble_chunked(cookies, extra)
                if v:
                    parts.append(f"{extra}={v}")
            line = "; ".join(parts)
            grok_lines[prof] = line
            results["grok_candidates"][prof] = {
                "has_sso": True, "has_sso_rw": "sso-rw=" in line,
                "has_cf_clearance": "cf_clearance=" in line,
                "cookie_line_len": len(line),
            }
            print(f"  grok candidate from profile {prof!r}: sso len={len(sso)} "
                  f"sso-rw={'sso-rw=' in line} cf_clearance={'cf_clearance=' in line}")
        else:
            names = sorted({c["name"] for c in cookies})
            print(f"  profile {prof!r}: no grok sso cookie (names={names[:10]})")

    # ---- 3. verify chatgpt candidates ----
    best_cgpt = None
    for prof, token, extras in cgpt_candidates:
        v = verify_chatgpt(token)
        results["verifications"][f"chatgpt-web@{prof}"] = v
        print(f"  verify chatgpt@{prof}: verified={v['verified']} status={v['status']} "
              f"cf_mitigated={v.get('cf_mitigated')} detail={v['detail'][:90]}")
        if v["verified"] and best_cgpt is None:
            best_cgpt = (prof, token)

    # ---- 4. verify grok candidates (best-effort) ----
    best_grok = None
    for prof, line in grok_lines.items():
        v = verify_grok(line)
        results["verifications"][f"grok-web@{prof}"] = v
        print(f"  verify grok@{prof}: verified={v['verified']} status={v['status']} "
              f"anti_bot={v.get('anti_bot_wall')} detail={v['detail'][:90]}")
        if best_grok is None:
            best_grok = (prof, line, v)

    # ---- 5. store values (gitignored, T11) ----
    store = {}
    if os.path.exists(KEYS_PATH):
        try:
            store = json.loads(open(KEYS_PATH, encoding="utf-8").read())
        except Exception:
            store = {}
    if best_cgpt:
        store["browser_session:chatgpt-web"] = {
            "value": best_cgpt[1], "profile": best_cgpt[0],
            "harvested_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "rookie-cookies-elevated-v2",
            "upstream_verified": True,
        }
    if best_grok:
        store["browser_session:grok-web"] = {
            "value": best_grok[1], "profile": best_grok[0],
            "harvested_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "rookie-cookies-elevated-v2",
            "upstream_verified": bool(best_grok[2].get("verified")),
            "note": "python-verify may be anti-bot-walled; OmniRoute TLS validator is authoritative",
        }
    json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)
    print(f"stored {len(store)} session keys -> {KEYS_PATH} (values masked in logs)")

    # ---- 6. inject into OmniRoute ----
    # chatgpt: only if upstream-verified. grok: inject if sso present (OmniRoute's
    # own TLS-client validator is authoritative; deactivate if it fails).
    to_inject = {}
    if best_cgpt:
        to_inject["chatgpt-web"] = best_cgpt[1]
    if best_grok:
        to_inject["grok-web"] = best_grok[1]

    if to_inject:
        from omniroute_api import OmniRouteAPI
        api = OmniRouteAPI()
        if not api.login():
            print("ERROR: could not authenticate to OmniRoute management API")
        else:
            conns = api.get_connections()
            for slug, cred in to_inject.items():
                existing = next((c for c in conns if c.get("provider") == slug), None)
                if existing:
                    upd = api.update_connection(existing["id"],
                                                {"apiKey": cred, "isActive": True})
                    cid = existing["id"]
                else:
                    r = api.session.post(f"{api.api}/providers",
                                         json={"provider": slug, "authType": "apikey",
                                               "apiKey": cred, "name": slug,
                                               "isActive": True},
                                         timeout=120)
                    try:
                        upd = {"http_status": r.status_code, "body": r.json()}
                    except Exception:
                        upd = {"http_status": r.status_code, "body": r.text[:300]}
                    cid = (upd.get("body") or {}).get("id") if isinstance(upd.get("body"), dict) else None
                results["injections"][slug] = {
                    "http": upd.get("http_status"),
                    "body": str(upd.get("body"))[:300]}
                print(f"  inject {slug}: HTTP {upd.get('http_status')} "
                      f"{str(upd.get('body'))[:150]}")
                # OmniRoute's OWN authoritative test (TLS-impersonating validator)
                if cid:
                    t = api.test_connection(cid)
                    results["injections"][slug]["omniroute_test"] = t
                    res = t.get("result", {})
                    print(f"    OmniRoute test: HTTP {t.get('http_status')} "
                          f"valid={res.get('valid')} error={str(res.get('error'))[:120]}")

    json.dump(results, open(RESULTS_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nresults -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
