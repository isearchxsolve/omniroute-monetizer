#!/usr/bin/env python3
"""Verify harvested Gemini key UPSTREAM (200 OK required), then inject into
OmniRoute as a `gemini` apikey connection and test it there.

Anti-pattern #7: no injection without a live upstream HTTP 200.
T11-safe: keys read from gitignored state/generated_keys.json; masked output only.
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
import requests  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def verify_upstream(key):
    """Live test against generativelanguage.googleapis.com."""
    # 1) list models (cheap, proves auth) and pick a live generateContent model
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": key},
        params={"pageSize": 100},
        timeout=30,
    )
    if r.status_code != 200:
        return r.status_code, f"models list: {r.text[:200]}"
    models = r.json().get("models", [])
    candidates = [
        m["name"].split("/")[-1]
        for m in models
        if "generateContent" in (m.get("supportedGenerationMethods") or [])
    ]
    # Prefer flash-lite/flash (cheap), then anything stable
    preferred = [c for c in candidates if "flash-lite" in c]
    preferred += [c for c in candidates if "flash" in c and c not in preferred]
    preferred += [c for c in candidates if c not in preferred]
    if not preferred:
        return 500, "no generateContent-capable models found"
    model = preferred[0]
    # 2) actual generation (proves quota + inference)
    r2 = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": "Reply with the single word: ok"}]}],
              "generationConfig": {"maxOutputTokens": 16}},
        timeout=60,
    )
    if r2.status_code != 200:
        return r2.status_code, f"generateContent({model}): {r2.text[:200]}"
    try:
        txt = r2.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        txt = "(unparsed)"
    return 200, f"generation OK via {model}: {txt[:40]!r}"


def main():
    data = json.load(open(KEYS_FILE, encoding="utf-8"))
    entry = data.get("gemini", {})
    keys = entry.get("keys") or ([entry["key"]] if entry.get("key") else [])
    if not keys:
        print("[-] no gemini keys in generated_keys.json")
        return 1

    valid_key = None
    for k in keys:
        print(f"[*] verifying upstream: {mask(k)} ...")
        status, detail = verify_upstream(k)
        print(f"    HTTP {status} — {detail}")
        if status == 200:
            valid_key = k
            break

    if not valid_key:
        print("[-] NO key passed upstream verification. NOT injecting.")
        return 2
    print(f"[+] VERIFIED upstream: {mask(valid_key)}")

    # --- Inject into OmniRoute ---
    from omniroute_api import OmniRouteAPI  # noqa: E402
    from oauth_keepalive import resolve_password  # noqa: E402

    pw = resolve_password()
    if not pw:
        print("[-] no OmniRoute password resolvable")
        return 3
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return 3

    conns = api.get_connections()
    existing = [c for c in conns if (c.get("provider") or "").lower() == "gemini"]
    cid = None
    if existing:
        # reuse first gemini connection
        cid = existing[0]["id"]
        print(f"[*] updating existing gemini connection {cid}")
        res = api.update_connection(cid, {"apiKey": valid_key, "isActive": True})
        print(f"    update -> HTTP {res.get('http_status')}")
    else:
        payload = {
            "provider": "gemini",
            "name": "Gemini (autonomous harvest)",
            "authType": "apikey",
            "apiKey": valid_key,
            "isActive": True,
        }
        r = api.session.post(f"{api.api}/providers", json=payload, timeout=20)
        print(f"[*] POST /api/providers -> HTTP {r.status_code}")
        if r.status_code not in (200, 201):
            print(f"    body: {r.text[:200]}")
            return 4
        cid = r.json().get("id") or r.json().get("connection", {}).get("id")
        print(f"    created connection id={cid}")

    if not cid:
        print("[-] could not determine connection id")
        return 4

    # Sync models + test inside OmniRoute
    rs = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
    print(f"[*] sync-models -> HTTP {rs.status_code}")
    test = api.test_connection(cid)
    http = test.get("http_status")
    res = test.get("result") or {}
    ok = bool(http == 200 and isinstance(res, dict) and (res.get("valid") or res.get("success") or res.get("ok") or res.get("healthy")))
    print(f"[*] OmniRoute test -> HTTP {http}, valid={ok}, detail={json.dumps(res)[:200]}")

    # Record result
    result = {
        "provider": "gemini",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "upstream_verified": True,
        "key_masked": mask(valid_key),
        "connection_id": cid,
        "omniroute_test_valid": ok,
    }
    with open(os.path.join(ROOT, "state", "gemini_inject_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nRESULT: {json.dumps(result, indent=2)}")
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
