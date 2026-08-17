#!/usr/bin/env python3
"""Second-pass probe for the three near-misses from the deep probe.

  api-airforce : 429 'Global rate limit exceeded (1 requests per second)'
                 -> retry ONE request, spaced, with a real model id.
  chutes       : 429 on all models -> retry one model after a pause.
  nous-research: 400 'This request is not valid' -> try alternate payload
                 shapes (no extra params, different model id casing).

Zero Terra tokens. Output appended to state/provider_deep_probe.json under
'second_pass'.
"""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "provider_deep_probe.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json",
           "Content-Type": "application/json"}


def post(url, payload, timeout=45):
    try:
        r = requests.post(url, json=payload, timeout=timeout, headers=HEADERS)
        return r.status_code, r.text[:400]
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:150]}"


def main() -> int:
    results = {}

    # --- api-airforce: single spaced request ---
    print("api-airforce (spaced single request)...")
    time.sleep(2)
    payload = {"model": "devstral-latest",
               "messages": [{"role": "user", "content": "Reply with the single word: hello"}],
               "max_tokens": 16, "stream": False}
    st, body = post("https://api.airforce/v1/chat/completions", payload)
    results["api-airforce"] = {"status": st, "snippet": body}
    print(f"  [{st}] {body[:200]!r}")

    # --- chutes: one model after pause ---
    print("chutes (single request after pause)...")
    time.sleep(3)
    payload = {"model": "Qwen/Qwen3-32B-TEE",
               "messages": [{"role": "user", "content": "Reply with the single word: hello"}],
               "max_tokens": 16, "stream": False}
    st, body = post("https://llm.chutes.ai/v1/chat/completions", payload)
    results["chutes"] = {"status": st, "snippet": body}
    print(f"  [{st}] {body[:200]!r}")

    # --- nous-research: alternate payload shapes ---
    print("nous-research (payload shape experiments)...")
    base = "https://inference-api.nousresearch.com/v1/chat/completions"
    variants = [
        ("minimal", {"model": "qwen/qwen3.8-27b",
                     "messages": [{"role": "user", "content": "hi"}]}),
        ("no-slash", {"model": "qwen3.8-27b",
                      "messages": [{"role": "user", "content": "hi"}]}),
        ("max_tokens", {"model": "qwen/qwen3.8-27b",
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 16}),
    ]
    nous = []
    for name, payload in variants:
        time.sleep(1.5)
        st, body = post(base, payload)
        nous.append({"variant": name, "status": st, "snippet": body})
        print(f"  {name:12s} [{st}] {body[:180]!r}")
    results["nous-research"] = nous

    # merge into deep probe output
    data = json.loads(OUT.read_text(encoding="utf-8"))
    data["second_pass"] = {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "results": results}
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nupdated {OUT} with second_pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
