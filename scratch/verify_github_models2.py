#!/usr/bin/env python3
"""Verify GitHub PAT against GitHub Models via direct chat completion.
(The /models list endpoint 404s; go straight to /chat/completions.)
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")

BASE = "https://models.inference.ai.azure.com"


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def main():
    data = json.load(open(KEYS_FILE, encoding="utf-8"))
    key = data["github"]["key"]
    print(f"[*] testing stored PAT {mask(key)} ...")

    for model in ("gpt-4o-mini", "gpt-4o", "Llama-3.3-70B-Instruct", "Meta-Llama-3.1-8B-Instruct"):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
            "max_tokens": 16,
            "temperature": 0,
        }
        req = urllib.request.Request(BASE + "/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json",
                                              "User-Agent": "Mozilla/5.0"})
        try:
            r = urllib.request.urlopen(req, timeout=40)
            body = json.loads(r.read().decode())
            content = body["choices"][0]["message"]["content"]
            print(f"[+] {model} -> {r.status}, reply={content[:40]!r}")
            data["github-models"] = {"key": key, "verified": "full", "model": model,
                                     "source": "reused entry#35 github PAT", "date": "2026-08-16"}
            with open(KEYS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("[+] GITHUB MODELS VERIFIED; stored github-models verified=full")
            return 0
        except urllib.error.HTTPError as e:
            print(f"[-] {model} -> HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
        except Exception as e:
            print(f"[-] {model} failed: {e}")
    print("[-] no model worked")
    return 1


if __name__ == "__main__":
    sys.exit(main())
