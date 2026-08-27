# -*- coding: utf-8 -*-
"""Create 7 chrome-backed seat files for the signed-in uncovered tabs (worklog #1105).

These seats carry NO recorded bytes — the live signed-in tab in the :9222 providers
profile IS the credential (Adapter Thesis). dispatchable via has_chrome.
"""
import json, pathlib, time

SECRETS = pathlib.Path("state/secrets")
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

SEATS = [
    ("copilot.microsoft.com", "session_copilot_msft.json", "Microsoft Copilot"),
    ("claude.ai",             "session_claude_ai.json",    "Claude (Anthropic)"),
    ("grok.com",              "session_grok_com.json",     "Grok (xAI)"),
    ("duck.ai",               "session_duck_ai.json",      "Duck.ai (DuckDuckGo)"),
    ("genspark.ai",           "session_genspark_ai.json",  "Genspark Super Agent"),
    ("v0.app",                "session_v0_app.json",       "v0 (Vercel)"),
    ("yi.baichuan-ai.com",    "session_yi_baichuan.json",  "Baichuan Yi (medical)"),
]

for host, fname, site in SEATS:
    p = SECRETS / fname
    if p.exists():
        print("SKIP (exists):", fname)
        continue
    raw = {
        "host": host,
        "modality": "chat",
        "site": site,
        "sentinel": "Reply exactly one word: Omni.",
        "updated_at": int(time.time()),
        "status": {
            "alive": True,
            "harvested_at": now,
            "reason": ("chrome_bridge_tab_coverage: signed-in tab verified in :9222 "
                       "providers profile (composer present, no login CTA); live tab "
                       "is the credential, no recorded bytes (worklog #1105)"),
        },
    }
    p.write_text(json.dumps(raw, indent=1), encoding="utf-8")
    print("created:", fname, "->", host)
