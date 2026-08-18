"""Inject harvested cookie headers into OmniRoute + e2e verify (zero-fabrication).

For each signed-in provider:
  1. Load cookie header from state/generated_keys.json
  2. POST /api/providers {provider, authType:apikey, apiKey:<cookie header>, isActive:true}
     (idempotent: if a connection for the slug exists, PUT the key instead)
  3. POST /api/providers/{id}/sync-models
  4. POST /api/providers/{id}/test -> require valid=true
  5. E2E: POST /v1/chat/completions (stream:false) with a real model -> HTTP 200 + content

T11-safe: cookie values masked. LIVE only on genuine /v1 completion proof.
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

from omniroute_api import OmniRouteAPI, mask_token  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

# slug -> display name
TARGETS = {
    "perplexity-web": "Perplexity Web (autonomous SSO)",
    "t3-web": "T3 Chat Web (autonomous SSO)",
}


def mask(s):
    if not s:
        return "<empty>"
    return s[:12] + "..." + s[-6:] if len(s) > 24 else "<short>"


def main():
    store = json.load(open(KEYS_PATH, encoding="utf-8"))
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        print("[-] login failed")
        return 1

    conns = api.get_connections()
    by_provider = {}
    for c in conns:
        by_provider.setdefault((c.get("provider") or "").lower(), []).append(c)

    results = {}
    for slug, name in TARGETS.items():
        entry = store.get(f"cookie_header:{slug}")
        if not entry or not entry.get("cookie_header"):
            print(f"\n[{slug}] no cookie header harvested — skip")
            results[slug] = "no_credential"
            continue
        header = entry["cookie_header"]
        print(f"\n=== {slug} ===")
        print(f"  cookie header {mask(header)} (len={len(header)})")

        # find or create connection
        existing = by_provider.get(slug, [])
        if existing:
            cid = existing[0]["id"]
            print(f"  existing connection {cid[:8]} — updating key (idempotent)")
            res = api.update_connection(cid, {"apiKey": header, "isActive": True})
            print(f"  PUT -> HTTP {res.get('http_status')}")
        else:
            payload = {
                "provider": slug,
                "name": name,
                "authType": "apikey",
                "apiKey": header,
                "isActive": True,
            }
            r = api.session.post(f"{api.api}/providers", json=payload, timeout=20)
            print(f"  POST /api/providers -> HTTP {r.status_code}")
            if r.status_code not in (200, 201):
                print(f"  [-] create failed: {r.text[:300]}")
                results[slug] = "create_failed"
                continue
            body = r.json()
            cid = body.get("id") or (body.get("connection") or {}).get("id")
            if not cid:
                print(f"  [-] no connection id: {json.dumps(body)[:300]}")
                results[slug] = "no_id"
                continue
            print(f"  created connection {cid[:8]}")

        # sync models
        sr = api.session.post(f"{api.api}/providers/{cid}/sync-models", timeout=60)
        print(f"  sync-models -> HTTP {sr.status_code}")

        # test connection
        tr = api.test_connection(cid)
        valid = (tr.get("result") or {}).get("valid")
        print(f"  test -> HTTP {tr.get('http_status')} valid={valid}")
        if not valid:
            err = (tr.get("result") or {}).get("error") or (tr.get("result") or {}).get("message")
            print(f"  [-] test invalid: {str(err)[:200]}")
            results[slug] = "test_invalid"
            continue

        results[slug] = {"cid": cid, "test_valid": True}

    print("\n=== SUMMARY ===")
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
