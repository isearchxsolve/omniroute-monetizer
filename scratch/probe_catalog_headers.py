#!/usr/bin/env python3
"""Decisive runtime test: hit /api/models/catalog and dump ALL response headers.
The diagnostic headers expose the effective cacheTTL. With DB holding 600001:
  - read path Zod-validates -> effective TTL = 60000 (fallback)
  - read path raw           -> effective TTL = 600001
"""
import requests

BASE = "http://127.0.0.1:20199"
s = requests.Session()

# login
r = s.post(BASE + "/api/auth/login", json={"password": "sandbox-test-password-2026"}, timeout=60)
print("login:", r.status_code)

# hit catalog endpoint, dump all headers
r = s.get(BASE + "/api/models/catalog", timeout=120)
print("catalog status:", r.status_code)
print("=== ALL RESPONSE HEADERS ===")
for k, v in r.headers.items():
    print(f"  {k}: {v}")
print("=== body (first 300 chars) ===")
print(r.text[:300])
