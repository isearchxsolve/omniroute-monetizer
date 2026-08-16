#!/usr/bin/env python3
"""Verify the clipboard-harvested Gemini key UPSTREAM (zero-fabrication mandate).

Steps:
  1. GET /v1beta/models?key=... (auth check)
  2. POST generateContent with a tiny prompt (usability check)
  3. If 200: persist to state/generated_keys.json (gitignored), masked output only.
T11-safe: never prints the full key.
"""
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
import requests  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP = os.path.join(ROOT, "state", "clipboard_key.tmp")
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")

BASE = "https://generativelanguage.googleapis.com/v1beta"


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def main():
    key = open(TMP, encoding="utf-8").read().strip()
    if not key:
        print("[-] clipboard temp file empty")
        return 1
    print(f"[*] testing key {mask(key)} (len={len(key)})")

    # 1) auth: list models
    r = requests.get(f"{BASE}/models", params={"key": key, "pageSize": 5}, timeout=30)
    print(f"[*] GET /models -> HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"[-] auth failed: {r.text[:300]}")
        return 2
    models = [m.get("name") for m in r.json().get("models", [])]
    print(f"[+] authenticated. sample models: {models[:5]}")

    # 2) usability: tiny generation (try a few model names)
    ok_model = None
    last_err = ""
    for model in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-flash-latest"):
        try:
            r2 = requests.post(
                f"{BASE}/models/{model}:generateContent",
                params={"key": key},
                json={"contents": [{"parts": [{"text": "Reply with the single word: ok"}]}],
                      "generationConfig": {"maxOutputTokens": 8}},
                timeout=60,
            )
            if r2.status_code == 200:
                ok_model = model
                print(f"[+] generateContent OK on {model}")
                break
            last_err = f"{model}: HTTP {r2.status_code} {r2.text[:200]}"
            print(f"[!] {last_err}")
        except Exception as e:
            last_err = f"{model}: {type(e).__name__}: {e}"
            print(f"[!] {last_err}")

    if not ok_model:
        print("[-] key authenticates but no model usable (likely quota/billing on this project)")
        print(f"    last error: {last_err}")
        # still save as auth-only so we have the record
        save(key, verified="auth_only", error=last_err)
        return 3

    save(key, verified="full", model=ok_model)
    print(f"[+] VERIFIED: key {mask(key)} fully usable via {ok_model}")
    return 0


def save(key, verified, model=None, error=None):
    data = {}
    if os.path.exists(KEYS_FILE):
        try:
            data = json.load(open(KEYS_FILE, encoding="utf-8"))
        except Exception:
            data = {}
    data["gemini"] = {
        "key": key,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "clipboard_human_assisted",
        "verified": verified,
        "model": model,
        "error": error,
    }
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[*] saved to state/generated_keys.json (verified={verified})")
    # remove temp clipboard file
    try:
        os.remove(TMP)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
