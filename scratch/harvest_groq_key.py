#!/usr/bin/env python3
"""Harvest Groq key from clipboard -> verify upstream -> store (T11-safe).

Zero-fabrication: only marks verified=full after a real 200 from Groq API.
Groq keys look like gsk_...
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")

GROQ_MODELS = "https://api.groq.com/openai/v1/models"
GROQ_CHAT = "https://api.groq.com/openai/v1/chat/completions"


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def get_clipboard():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        capture_output=True, text=True, timeout=15)
    return (out.stdout or "").strip()


def main():
    clip = get_clipboard()
    if not clip:
        print("[-] clipboard empty")
        return 1
    # Groq keys: gsk_ followed by ~50 chars
    m = re.search(r"gsk_[A-Za-z0-9]{20,}", clip)
    if not m:
        print(f"[-] no gsk_ key found in clipboard (len={len(clip)}, starts={clip[:6]!r})")
        return 2
    key = m.group(0)
    print(f"[*] harvested key {mask(key)} (len={len(key)})")

    # 1) verify: list models (Groq CDN blocks default urllib UA -> send browser UA)
    req = urllib.request.Request(GROQ_MODELS, headers={"Authorization": f"Bearer {key}",
                                                       "User-Agent": "Mozilla/5.0"})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        models = json.loads(r.read().decode())
        ids = [m.get("id") for m in models.get("data", [])]
        print(f"[+] GET /models -> {r.status}, {len(ids)} models")
    except Exception as e:
        print(f"[-] GET /models failed: {e}")
        return 3

    # 2) verify: real chat completion (valid payload, not a keep-alive ping)
    # pick a live chat model dynamically (Groq renamed ids to prefixed form)
    model = None
    for pref in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-20b",
                 "meta-llama/llama-4-scout-17b-16e-instruct", "groq/compound-mini"):
        if pref in ids:
            model = pref
            break
    if model is None:
        # fall back to first active text-in/text-out model
        for m in models.get("data", []):
            if m.get("active") and "text" in (m.get("input_modalities") or []):
                model = m.get("id")
                break
    print(f"[*] using model: {model}")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    req = urllib.request.Request(
        GROQ_CHAT,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0"})
    verified = "models_only"
    try:
        r = urllib.request.urlopen(req, timeout=30)
        body = json.loads(r.read().decode())
        content = body["choices"][0]["message"]["content"]
        print(f"[+] chat completion -> {r.status}, reply={content[:40]!r}")
        verified = "full"
    except Exception as e:
        print(f"[!] chat completion failed (models OK): {e}")

    # 3) store
    data = {}
    if os.path.exists(KEYS_FILE):
        data = json.load(open(KEYS_FILE, encoding="utf-8"))
    data["groq"] = {"key": key, "verified": verified, "source": "human-in-the-loop clipboard",
                    "date": "2026-08-16"}
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] stored groq key verified={verified} in state/generated_keys.json")
    return 0 if verified == "full" else 4


if __name__ == "__main__":
    sys.exit(main())
