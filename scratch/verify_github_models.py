#!/usr/bin/env python3
"""Verify the stored GitHub PAT against GitHub Models API (zero-fabrication).

GitHub Models endpoint: https://models.inference.ai.azure.com
Auth: Bearer <github PAT>. No new signup needed — reuses entry #35 PAT.
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
    entry = data.get("github")
    if not entry or not entry.get("key"):
        print("[-] no github key stored")
        return 1
    key = entry["key"]
    print(f"[*] testing stored PAT {mask(key)} against GitHub Models ...")

    # 1) list models
    req = urllib.request.Request(BASE + "/models",
                                 headers={"Authorization": f"Bearer {key}",
                                          "User-Agent": "Mozilla/5.0"})
    try:
        r = urllib.request.urlopen(req, timeout=25)
        models = json.loads(r.read().decode())
        ids = [m.get("name") or m.get("id") for m in (models if isinstance(models, list) else models.get("data", []))]
        print(f"[+] GET /models -> {r.status}, {len(ids)} models")
        print(f"    sample: {ids[:12]}")
    except urllib.error.HTTPError as e:
        print(f"[-] GET /models -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        return 2
    except Exception as e:
        print(f"[-] GET /models failed: {e}")
        return 2

    # 2) real chat completion with a known GitHub Models model
    model = None
    for cand in ("gpt-4o-mini", "gpt-4o", "Llama-3.3-70B-Instruct", "Meta-Llama-3.1-8B-Instruct"):
        if cand in ids:
            model = cand
            break
    if model is None and ids:
        model = ids[0]
    print(f"[*] using model: {model}")
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
        print(f"[+] chat completion -> {r.status}, reply={content[:40]!r}")
        print("[+] GITHUB MODELS VERIFIED — PAT works, no signup needed")
        # mark verified for injection
        data["github-models"] = {"key": key, "verified": "full",
                                 "source": "reused entry#35 github PAT", "date": "2026-08-16"}
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[+] stored github-models verified=full")
        return 0
    except urllib.error.HTTPError as e:
        print(f"[-] chat -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        return 3
    except Exception as e:
        print(f"[-] chat failed: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
