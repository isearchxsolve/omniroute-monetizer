#!/usr/bin/env python3
"""Diagnose Groq 403: print response body + headers (T11-safe, no key printed)."""
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                     capture_output=True, text=True, timeout=15)
clip = (out.stdout or "").strip()
m = re.search(r"gsk_[A-Za-z0-9]{20,}", clip)
if not m:
    print("[-] no gsk_ key in clipboard")
    sys.exit(1)
key = m.group(0)

req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {key}",
                                      "User-Agent": "Mozilla/5.0"})
try:
    r = urllib.request.urlopen(req, timeout=20)
    print("status:", r.status)
    print(r.read().decode()[:500])
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code)
    print("headers:", dict(e.headers))
    body = e.read().decode(errors="replace")
    print("body:", body[:800])
except Exception as e:
    print("ERR:", type(e).__name__, e)
