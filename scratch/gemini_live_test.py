"""Definitive gemini-web LIVE test: real /v1/chat/completions through OmniRoute."""
import json
import time

import requests

BASE = "http://localhost:20128"
MODELS = [
    "gemini-web/gemini-3.5-flash",
    "gemini-web/gemini-3.1-flash-lite",
    "gemini-web/gemini-3.1-pro",
]

for model in MODELS:
    t0 = time.time()
    try:
        r = requests.post(
            f"{BASE}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: LIVE"}],
                "max_tokens": 20,
            },
            timeout=180,
        )
        dt = time.time() - t0
        print(f"--- {model}: HTTP {r.status_code} ({dt:.1f}s)")
        try:
            d = r.json()
            if r.status_code == 200:
                content = d["choices"][0]["message"]["content"]
                print("    CONTENT:", repr(content))
                print("    usage:", d.get("usage"))
                print("    LIVE=YES")
                break
            else:
                print("   ", json.dumps(d)[:800])
        except Exception as e:
            print("    parse error:", e)
            print("   ", r.text[:800])
    except requests.exceptions.RequestException as e:
        dt = time.time() - t0
        print(f"--- {model}: REQUEST FAILED ({dt:.1f}s): {e}")
