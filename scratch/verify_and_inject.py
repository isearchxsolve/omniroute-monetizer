#!/usr/bin/env python3
"""Verify a generated key UPSTREAM (200 OK required, anti-pattern #7), then
inject into the matching OmniRoute apikey connection and test it.
Never prints full keys. T11-safe."""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
import requests  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
SCRATCH = os.path.dirname(os.path.abspath(__file__))

PROVIDER = sys.argv[1] if len(sys.argv) > 1 else "openrouter"

UPSTREAM = {
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openrouter/auto",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-3-5-haiku-latest",
    },
    "github": {
        "url": "https://api.github.com/user",
        "model": None,
    },
}

# OmniRoute connection ids (from prior ground truth)
CONN_IDS = {
    "openrouter": "49aa144d-9005-4968-a6cd-a36e8a2e947f",
}


def mask(k):
    if not k:
        return "<none>"
    return k[:10] + "..." + k[-4:] if len(k) > 16 else k[:4] + "..."


def get_password():
    pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
    if pw:
        return pw
    for name in ("raise_catalog_ttl.py", "live_apply_ttl.py"):
        path = os.path.join(SCRATCH, name)
        if not os.path.exists(path):
            continue
        try:
            content = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        m = re.search(r'or\s+"([^"]{8,})"', content)
        if m:
            return m.group(1)
    return ""


def verify_upstream(provider, key):
    cfg = UPSTREAM[provider]
    if provider == "openrouter":
        r = requests.post(
            cfg["url"],
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": cfg["model"], "messages": [{"role": "user", "content": "Reply with the single word: ok"}], "max_tokens": 16},
            timeout=60,
        )
        return r.status_code, r.text[:300]
    if provider == "anthropic":
        r = requests.post(
            cfg["url"],
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": cfg["model"], "max_tokens": 16, "messages": [{"role": "user", "content": "Reply with the single word: ok"}]},
            timeout=60,
        )
        return r.status_code, r.text[:300]
    if provider == "github":
        r = requests.get(cfg["url"], headers={"Authorization": f"Bearer {key}", "Accept": "application/vnd.github+json"}, timeout=30)
        return r.status_code, r.text[:300]
    return 0, "unknown provider"


def main():
    data = json.load(open(KEYS_FILE, encoding="utf-8"))
    if PROVIDER not in data:
        print(f"ERROR: no generated key for {PROVIDER}")
        return 1
    key = data[PROVIDER]["key"]
    print(f"[*] {PROVIDER}: verifying upstream key {mask(key)} ...")
    status, body = verify_upstream(PROVIDER, key)
    print(f"[*] upstream HTTP {status}")
    if status != 200:
        print(f"[-] UPSTREAM VERIFICATION FAILED: {body[:200]}")
        print("[-] NOT injecting (anti-pattern #7: 200 OK required before injection)")
        return 2
    print(f"[+] {PROVIDER} key VERIFIED upstream (200 OK)")

    # Inject into OmniRoute
    sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))
    from omniroute_api import OmniRouteAPI  # noqa: E402

    pw = get_password()
    if not pw:
        print("[-] no OMNIROUTE_PASSWORD; cannot inject")
        return 3
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return 3
    conns = api.get_connections()
    cid = CONN_IDS.get(PROVIDER)
    target = None
    for c in conns:
        if cid and c.get("id") == cid:
            target = c
            break
    if target is None:
        # fallback: find apikey connections for this provider
        for c in conns:
            prov = (c.get("provider") or "").lower()
            if PROVIDER in prov and c.get("authType") == "apikey":
                target = c
                break
    if target is None:
        print(f"[-] no matching OmniRoute connection for {PROVIDER}")
        return 4
    existing = target.get("apiKey") or ""
    if existing == key:
        print(f"[~] connection {target['id']} already has this key; idempotent skip")
        return 0
    print(f"[*] injecting into connection {target['id']} (provider={target.get('provider')}, authType={target.get('authType')})")
    res = api.update_connection(target["id"], {"apiKey": key})
    print(f"[*] update_connection -> {json.dumps(res)[:200] if isinstance(res, dict) else res}")
    test = api.test_connection(target["id"])
    ok = False
    detail = ""
    if isinstance(test, dict):
        http = test.get("http_status")
        res = test.get("result") or {}
        detail = json.dumps(res)[:250]
        if http == 200 and isinstance(res, dict):
            ok = bool(res.get("valid") or res.get("success") or res.get("ok") or res.get("healthy"))
    print(f"[*] test_connection -> ok={ok} detail={detail}")
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
