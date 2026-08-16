#!/usr/bin/env python3
"""Verify GitHub PAT against GitHub Models using OmniRoute's actual endpoint
(models.github.ai/inference, X-GitHub-Api-Version header). Zero-fabrication.
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")

BASE = "https://models.github.ai/inference"
CATALOG = "https://models.github.ai/catalog/models"
HDRS = {"X-GitHub-Api-Version": "2026-03-10",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Mozilla/5.0"}


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def main():
    data = json.load(open(KEYS_FILE, encoding="utf-8"))
    key = data["github"]["key"]
    print(f"[*] testing stored PAT {mask(key)} against models.github.ai ...")

    # 1) catalog
    req = urllib.request.Request(CATALOG, headers={**HDRS, "Authorization": f"Bearer {key}"})
    ids = []
    try:
        r = urllib.request.urlopen(req, timeout=25)
        cat = json.loads(r.read().decode())
        items = cat if isinstance(cat, list) else cat.get("models", cat.get("data", []))
        ids = [m.get("id") or m.get("name") for m in items if isinstance(m, dict)]
        print(f"[+] GET catalog -> {r.status}, {len(ids)} models; sample={ids[:10]}")
    except urllib.error.HTTPError as e:
        print(f"[-] catalog -> HTTP {e.code}: {e.read().decode(errors='replace')[:250]}")
    except Exception as e:
        print(f"[-] catalog failed: {e}")

    # 2) chat completion
    model = None
    for cand in ("openai/gpt-4o-mini", "gpt-4o-mini", "openai/gpt-4o", "gpt-4o"):
        if cand in ids:
            model = cand
            break
    if model is None:
        model = next((i for i in ids if "gpt" in i.lower()), ids[0] if ids else "openai/gpt-4o-mini")
    print(f"[*] using model: {model}")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    req = urllib.request.Request(BASE + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={**HDRS, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=40)
        body = json.loads(r.read().decode())
        content = body["choices"][0]["message"]["content"]
        print(f"[+] chat completion -> {r.status}, reply={content[:40]!r}")
        data["github-models"] = {"key": key, "verified": "full", "model": model,
                                 "source": "reused entry#35 github PAT", "date": "2026-08-16"}
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[+] GITHUB MODELS VERIFIED; stored github-models verified=full")
        return 0
    except urllib.error.HTTPError as e:
        print(f"[-] chat -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        return 1
    except Exception as e:
        print(f"[-] chat failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
