#!/usr/bin/env python3
"""
Extract the exact, comprehensive catalog of all ~295 providers from omniroute_ui_diagnostic.
"""
import os
import sys
import re
import json
from pathlib import Path

p02 = Path("omniroute_ui_diagnostic/02_providers.json")
p_rows = Path("omniroute_ui_diagnostic/02_provider_rows.json")

providers = {}

if p02.exists():
    d = json.loads(p02.read_text(encoding="utf-8"))
    # Parse links
    for l in d.get("links", []):
        href = l.get("href", "")
        text = l.get("text", "").strip()
        # matches like /providers/openai or /dashboard/providers/openai
        m = re.search(r'/providers/([a-z0-9_\-]+)', href)
        if m:
            slug = m.group(1)
            if slug not in ["add", "new", "settings", "combos", "models"]:
                if slug not in providers:
                    providers[slug] = {"slug": slug, "name": text or slug, "sources": []}
                providers[slug]["sources"].append(href)

if p_rows.exists():
    rows = json.loads(p_rows.read_text(encoding="utf-8"))
    for r in rows:
        text = r.get("text", "")
        links = r.get("links", [])
        for l in links:
            href = l.get("href", "")
            m = re.search(r'/providers/([a-z0-9_\-]+)', href)
            if m:
                slug = m.group(1)
                if slug not in ["add", "new", "settings", "combos", "models"]:
                    if slug not in providers:
                        providers[slug] = {"slug": slug, "name": l.get("text") or slug, "sources": []}
                    providers[slug]["sources"].append(href)

# Also inspect body text from 02_providers.json to capture category sections
if p02.exists():
    body = d.get("bodyText", "")
    # Parse section headings like 'API Key (192)', 'Free Tier (126)', 'OAuth (20)', 'Web Cookie (31)', 'Local (12)'
    categories = re.findall(r'([A-Za-z0-9\s&]+)\s*\((\d+)\)', body)
    print("Detected Provider Categories in UI:")
    for cat, count in categories:
        print(f"  - {cat.strip()}: {count} providers")

print(f"\nTotal unique providers extracted: {len(providers)}")
sample = sorted(list(providers.keys()))[:30]
print(f"Sample providers: {sample}")

# Output catalog
catalog_file = Path("state/all_295_providers_catalog.json")
catalog_file.write_text(json.dumps({
    "total_count": len(providers),
    "providers": providers
}, indent=2), encoding="utf-8")
print(f"Saved complete catalog to {catalog_file}")
