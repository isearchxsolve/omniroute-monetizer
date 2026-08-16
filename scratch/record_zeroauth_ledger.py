#!/usr/bin/env python3
"""Record zero-auth batch verification results in the execution ledger.
All 8 cloud candidates failed upstream verification (0/8) + g4f-pollinations 402.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LEDGER = os.path.join(ROOT, "state", "all_296_providers_execution_ledger.json")

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

UPDATES = {
    "pollinations": ("BLOCKED_AUTH_REQUIRED",
        "Upstream gen.pollinations.ai returns HTTP 401: 'Authentication required. Please provide an API key'. authType=optional in OmniRoute config does not mean keyless upstream access."),
    "duckduckgo-web": ("BLOCKED_NO_SESSION",
        "DuckDuckGo duckchat requires a VQD session token; status endpoint returned no x-vqd-4 without browser cookies/session. Needs a real browser session, not plain HTTP."),
    "theoldllm": ("BLOCKED_FORBIDDEN",
        "Upstream theoldllm.vercel.app/api/chatgpt returns HTTP 403 Forbidden (Vercel edge block)."),
    "hackclub": ("BLOCKED_AUTH_REQUIRED",
        "Models endpoint open (discovered qwen/qwen3.8-27b) but chat endpoint returns HTTP 401 'Authentication required'."),
    "g4f-gemini": ("BLOCKED_CREDITS",
        "HTTP 402: 'No cake credits. Bake proof-of-work cakes at g4f.dev/chat to earn anonymous usage, or sign up at g4f.dev/members.html.'"),
    "g4f-groq": ("BLOCKED_CREDITS",
        "HTTP 402 cake-credits wall (same as g4f-gemini)."),
    "g4f-nvidia": ("BLOCKED_CREDITS",
        "HTTP 402 cake-credits wall; models endpoint also empty."),
    "g4f-pollinations": ("BLOCKED_CREDITS",
        "Models endpoint 200 (213 models) but chat returns HTTP 402: 'No cake credits. Bake proof-of-work cakes at g4f.dev/chat...'"),
    "uncloseai": ("BLOCKED_UPSTREAM_DOWN",
        "Upstream hermes.ai.unturf.com returns HTTP 502 (bad gateway); models endpoint unreachable."),
}

with open(LEDGER, encoding="utf-8") as f:
    d = json.load(f)

changed = 0
for slug, (status, blocker) in UPDATES.items():
    e = d["providers"].get(slug)
    if e is None:
        print(f"[!] missing slug: {slug}")
        continue
    e["status"] = status
    e["details"] = dict(e.get("details") or {})
    e["details"]["blocker"] = blocker
    e["details"]["attempted"] = (f"{TODAY}: zero-auth batch — upstream chat completion attempted with no key "
                                 f"(scratch/batch_verify_zeroauth.py). Zero-fabrication: not marked live without a 200.")
    e["details"]["safe_handling"] = "Suppressed from cascades to prevent 404/timeout stalls"
    changed += 1
    print(f"[+] {slug} -> {status}")

d["timestamp"] = datetime.now(timezone.utc).isoformat()
# recompute unconfigured count from actual statuses for internal consistency
d["unconfigured_external_count"] = sum(
    1 for v in d["providers"].values() if v.get("status") == "EXTERNAL_ACCOUNT_REQUIRED")

with open(LEDGER, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

import collections
c = collections.Counter(v.get("status") for v in d["providers"].values())
print(f"\nupdated {changed} entries")
print("counts:", dict(c))
print("live:", d["live_tested_healthy_count"], "connected:", d["connected_providers_count"],
      "unconfigured:", d["unconfigured_external_count"])
