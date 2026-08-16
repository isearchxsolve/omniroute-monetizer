#!/usr/bin/env python3
"""Verify g4f-pollinations (free no-key reverse proxy) upstream. Zero-fabrication."""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

MODELS = "https://g4f.space/api/pollinations/v1/models"
CHAT = "https://g4f.space/api/pollinations/v1/chat/completions"
HDRS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}


def main():
    # 1) models
    req = urllib.request.Request(MODELS, headers=HDRS)
    try:
        r = urllib.request.urlopen(req, timeout=25)
        data = json.loads(r.read().decode())
        ids = [m.get("id") for m in data.get("data", [])]
        print(f"[+] GET /models -> {r.status}, {len(ids)} models; sample={ids[:10]}")
    except urllib.error.HTTPError as e:
        print(f"[-] models -> HTTP {e.code}: {e.read().decode(errors='replace')[:250]}")
        return 1
    except Exception as e:
        print(f"[-] models failed: {e}")
        return 1

    # 2) chat
    model = next((i for i in ids if i in ("openai", "openai-fast", "mistral")), ids[0] if ids else "openai")
    print(f"[*] using model: {model}")
    payload = {"model": model,
               "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
               "max_tokens": 16, "temperature": 0}
    req = urllib.request.Request(CHAT, data=json.dumps(payload).encode(), headers=HDRS)
    try:
        r = urllib.request.urlopen(req, timeout=45)
        body = json.loads(r.read().decode())
        content = body["choices"][0]["message"]["content"]
        print(f"[+] chat -> {r.status}, reply={content[:40]!r}")
        print("[+] G4F-POLLINATIONS VERIFIED (no key needed)")
        return 0
    except urllib.error.HTTPError as e:
        print(f"[-] chat -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        return 2
    except Exception as e:
        print(f"[-] chat failed: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
