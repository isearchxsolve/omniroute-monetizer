#!/usr/bin/env python3
"""End-to-end verify chatgpt-web + grok-web connections serve real inference via /v1.
Step 1: OmniRoute's OWN authoritative test (TLS-impersonating validator).
Step 2: real /v1/chat/completions with valid standard payloads (AGENTS.md rule 3).
Redacted output (T11)."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

import requests  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

RESULTS = os.path.join(ROOT, "state", "e2e_chatgpt_grok_results.json")
report = {"providers": {}}

api = OmniRouteAPI(password=resolve_password())
api.login()
conns = api.get_connections()

r = requests.get(f"{api.base}/v1/models", timeout=30)
all_models = r.json().get("data", []) if r.status_code == 200 else []
print(f"total /v1 models = {len(all_models)}")

for slug in ("chatgpt-web", "grok-web"):
    print(f"\n===== {slug} =====")
    entry = {}
    conn = next((c for c in conns if c.get("provider") == slug), None)
    if not conn:
        print(f"[-] no {slug} connection")
        entry["error"] = "no connection"
        report["providers"][slug] = entry
        continue
    cid = conn["id"]
    print(f"conn {cid} isActive={conn.get('isActive')}")

    # Step 1: OmniRoute's authoritative test
    t = api.test_connection(cid)
    res = t.get("result", {})
    entry["omniroute_test"] = {"http": t.get("http_status"),
                               "valid": res.get("valid"),
                               "error": str(res.get("error"))[:200]}
    print(f"  OmniRoute test: HTTP {t.get('http_status')} valid={res.get('valid')} "
          f"error={str(res.get('error'))[:150]}")

    # Step 2: models attributed to this provider
    prov_models = [m.get("id") for m in all_models
                   if m.get("providerId") == cid
                   or str(m.get("provider", "")).lower() == slug
                   or slug in str(m.get("id", "")).lower()]
    entry["models"] = prov_models[:15]
    print(f"  attributed models ({len(prov_models)}): {prov_models[:8]}")

    if not prov_models:
        entry["e2e"] = "no models attributed — provider test may have failed"
        report["providers"][slug] = entry
        continue

    # Step 3: real completion on first model
    target = prov_models[0]
    payload = {"model": target,
               "messages": [{"role": "user",
                             "content": "Reply with exactly one word: hello"}],
               "max_tokens": 32, "temperature": 0, "stream": False}
    print(f"  probing /v1/chat/completions model={target}")
    try:
        resp = requests.post(f"{api.base}/v1/chat/completions",
                             json=payload, timeout=120)
        entry["e2e"] = {"model": target, "http": resp.status_code}
        print(f"  HTTP {resp.status_code}")
        if resp.status_code == 200:
            j = resp.json()
            choice = (j.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content", "")
            entry["e2e"]["content"] = content[:80]
            entry["e2e"]["usage"] = j.get("usage")
            entry["e2e"]["live"] = True
            print(f"  content={content[:80]!r} usage={j.get('usage')}")
            print(f"[+] {slug} END-TO-END LIVE")
        else:
            entry["e2e"]["body"] = resp.text[:300]
            entry["e2e"]["live"] = False
            print(f"  body={resp.text[:300]}")
            print(f"[-] {slug} inference probe failed")
    except Exception as e:
        entry["e2e"] = {"model": target, "error": f"{type(e).__name__}: {e}"}
        print(f"  probe exception: {e}")

    report["providers"][slug] = entry

json.dump(report, open(RESULTS, "w", encoding="utf-8"), indent=2)
print(f"\nreport -> {RESULTS}")
