#!/usr/bin/env python3
"""Stage 1 verification: authenticate to the SANDBOX OmniRoute (port 20199),
inspect the model-catalog cache TTL setting, raise it toward the new 600000ms
ceiling enabled by the hotfix, and verify persistence via re-GET.

T11-safe: sandbox-only credentials, no live secrets, nothing sensitive printed.
"""
import json
import sys
import requests

BASE = "http://127.0.0.1:20199"
PASSWORD = "sandbox-test-password-2026"  # sandbox-only, not a live secret

s = requests.Session()


def main():
    # 1. Login
    r = s.post(f"{BASE}/api/auth/login", json={"password": PASSWORD}, timeout=30)
    print(f"[login] HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"[login] FAILED: {r.text[:300]}")
        sys.exit(1)

    # 2. Discover settings endpoint(s)
    for path in ("/api/settings", "/api/config", "/api/runtime-settings"):
        try:
            rr = s.get(f"{BASE}{path}", timeout=30)
            print(f"[probe] GET {path} -> HTTP {rr.status_code}")
            if rr.status_code == 200:
                try:
                    data = rr.json()
                except Exception:
                    data = None
                if data is not None:
                    blob = json.dumps(data)
                    if "modelCatalogCacheTtlMs" in blob or "CacheTtl" in blob or "cache" in blob.lower():
                        print(f"[probe] {path} contains cache-related keys")
                        # print top-level keys only (avoid dumping secrets)
                        if isinstance(data, dict):
                            print(f"[probe] top-level keys: {sorted(data.keys())[:60]}")
        except Exception as e:
            print(f"[probe] GET {path} error: {e}")

    # 3. Search for the TTL key anywhere in settings
    rr = s.get(f"{BASE}/api/settings", timeout=30)
    if rr.status_code == 200:
        try:
            data = rr.json()
            _find_ttl(data, path="$")
        except Exception as e:
            print(f"[settings] parse error: {e}")


def _find_ttl(obj, path):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if "ttl" in k.lower() or "cache" in k.lower():
                if isinstance(v, (int, float, str, bool)) or v is None:
                    print(f"[ttl-candidate] {p} = {v!r}")
                else:
                    print(f"[ttl-candidate] {p} = <{type(v).__name__}>")
            _find_ttl(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20]):
            _find_ttl(v, f"{path}[{i}]")


if __name__ == "__main__":
    main()
