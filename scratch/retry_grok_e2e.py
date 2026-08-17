#!/usr/bin/env python3
"""Retry grok-web e2e after the Cloudflare anti-bot rate-limit window resets.
OmniRoute's validator said the sso cookie is fine — IP-reputation block,
'reset after 24s'. Retries with backoff across all 4 grok-web models."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

import requests  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

RESULTS = os.path.join(ROOT, "state", "e2e_grok_retry_results.json")
api = OmniRouteAPI(password=resolve_password())
api.login()

MODELS = ["grok-web/fast", "grok-web/expert", "grok-web/heavy",
          "grok-web/grok-420-computer-use-sa"]
report = {"attempts": []}

for attempt in range(4):
    if attempt:
        wait = 30 * attempt
        print(f"\n-- waiting {wait}s for anti-bot window reset --")
        time.sleep(wait)
    for model in MODELS:
        payload = {"model": model,
                   "messages": [{"role": "user",
                                 "content": "Reply with exactly one word: hello"}],
                   "max_tokens": 32, "temperature": 0, "stream": False}
        try:
            resp = requests.post(f"{api.base}/v1/chat/completions",
                                 json=payload, timeout=120)
        except Exception as e:
            print(f"  {model}: exception {e}")
            continue
        att = {"attempt": attempt + 1, "model": model, "http": resp.status_code}
        if resp.status_code == 200:
            j = resp.json()
            content = ((j.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            att["content"] = content[:80]
            att["usage"] = j.get("usage")
            att["live"] = True
            report["attempts"].append(att)
            json.dump(report, open(RESULTS, "w", encoding="utf-8"), indent=2)
            print(f"  {model}: HTTP 200 content={content[:60]!r} usage={j.get('usage')}")
            print("[+] GROK-WEB END-TO-END LIVE")
            sys.exit(0)
        att["body"] = resp.text[:200]
        report["attempts"].append(att)
        print(f"  {model}: HTTP {resp.status_code} {resp.text[:120]}")

json.dump(report, open(RESULTS, "w", encoding="utf-8"), indent=2)
print(f"\n[-] grok-web still anti-bot blocked after retries -> {RESULTS}")
sys.exit(1)
