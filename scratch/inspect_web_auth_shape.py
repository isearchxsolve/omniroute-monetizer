#!/usr/bin/env python3
"""What does OmniRoute need to connect chatgpt-web and gemini-web?

Reads the extracted catalog (authHint/authType/freeNote) and the baseUrl map
for the two harvestable providers, and inspects how any EXISTING OmniRoute
connections store web/cookie/bearer auth (providerSpecificData shape) so we
know the injection format. Read-only. T11-safe (no secret values printed).
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

cat = json.load(open(os.path.join(ROOT, "state", "provider_catalog_extracted.json"), encoding="utf-8"))
base = json.load(open(os.path.join(ROOT, "state", "provider_baseurls.json"), encoding="utf-8"))

# catalog may be a dict or list
catmap = cat if isinstance(cat, dict) else {c.get("id"): c for c in cat}

for slug in ("chatgpt-web", "gemini-web"):
    print(f"\n===== {slug} =====")
    c = catmap.get(slug) or catmap.get(slug, {})
    if isinstance(c, dict):
        for k in ("id", "alias", "name", "authHint", "authType", "freeNote",
                  "signupUrl", "hasFree", "website"):
            if c.get(k) not in (None, ""):
                print(f"  catalog.{k}: {c.get(k)}")
    b = base.get(slug)
    if isinstance(b, dict):
        for k in ("baseUrl", "authType", "authHeader"):
            if b.get(k):
                print(f"  baseurls.{k}: {b.get(k)}")
        models = b.get("models")
        if models:
            print(f"  baseurls.models: {len(models)} -> {models[:6]}")

# How do existing connections store web/cookie/bearer auth?
print("\n===== existing connection auth shapes (providerSpecificData keys) =====")
try:
    from playwright.sync_api import sync_playwright  # noqa
except Exception:
    pass
# read the saved connections snapshot if present
for fn in ("omniroute_provider_recovery/connections_before.json",):
    p = os.path.join(ROOT, fn)
    if os.path.exists(p):
        data = json.load(open(p, encoding="utf-8"))
        conns = data if isinstance(data, list) else data.get("connections", [])
        seen = set()
        for c in conns:
            prov = c.get("provider")
            at = c.get("authType")
            psd = c.get("providerSpecificData") or {}
            key = (prov, at)
            if key in seen:
                continue
            seen.add(key)
            psd_keys = sorted(psd.keys()) if isinstance(psd, dict) else type(psd).__name__
            print(f"  {str(prov):22s} authType={str(at):8s} providerSpecificData keys={psd_keys}")
        break
