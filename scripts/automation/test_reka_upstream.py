"""Test Reka upstream API with the extracted key.
"""
from __future__ import annotations
import sys
import json
import requests

sys.stdout.reconfigure(encoding="utf-8")

def test_reka_upstream():
    # The key extracted from Button 5 clipboard read
    # Let's read from powershell clipboard or run directly
    import subprocess
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True)
    key = (out.stdout or "").strip()
    print(f"[+] Key from clipboard: {key[:6]}...{key[-4:]} (len={len(key)})")
    
    headers = {
        "X-Api-Key": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    # 1. Models endpoint
    for url in ("https://api.reka.ai/v1/models", "https://api.reka.ai/chat", "https://api.reka.ai/v1/chat/completions"):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            print(f"GET {url} -> HTTP {r.status_code} | {r.text[:200]}")
        except Exception as e:
            print(f"GET {url} -> Error: {e}")
            
    # 2. Chat completion with reka-flash / reka-core / reka-edge
    for m in ("reka-flash", "reka-core", "reka-edge", "reka-flash-20240226"):
        try:
            payload = {
                "model": m,
                "messages": [{"role": "user", "content": "Say 'OK' and nothing else"}],
                "max_tokens": 10
            }
            cr = requests.post("https://api.reka.ai/v1/chat/completions", headers=headers, json=payload, timeout=15)
            print(f"POST /v1/chat/completions ({m}) -> HTTP {cr.status_code} | {cr.text[:200]}")
        except Exception as e:
            print(f"POST {m} -> Error: {e}")

if __name__ == "__main__":
    test_reka_upstream()
