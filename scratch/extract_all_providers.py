#!/usr/bin/env python3
"""
Extract all defined providers from OmniRoute's JS bundle.
"""
import os
import sys
import re
import json
from pathlib import Path

bundle_dir = Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist")
if not bundle_dir.exists():
    print("Bundle dir not found")
    sys.exit(1)

providers_found = set()
slugs_found = set()

# Search for provider metadata objects or lists
pattern = re.compile(r'["\'](?:provider|providerId|slug)["\']\s*:\s*["\']([a-z0-9_\-]+)["\']', re.I)

for js_file in bundle_dir.rglob("*.js"):
    try:
        content = js_file.read_text(encoding="utf-8", errors="ignore")
        matches = pattern.findall(content)
        for m in matches:
            if len(m) > 2 and len(m) < 40 and not m.startswith("0") and not m.isdigit():
                slugs_found.add(m)
    except Exception:
        pass

print(f"Total unique slug matches found across bundle: {len(slugs_found)}")

# Also look for links in 02_providers.json
p02 = Path("omniroute_ui_diagnostic/02_providers.json")
if p02.exists():
    d = json.loads(p02.read_text(encoding="utf-8"))
    links = d.get("links", [])
    ui_providers = set()
    for l in links:
        href = l.get("href", "")
        # /providers/... or /dashboard/providers/...
        m = re.search(r'/providers/([a-z0-9_\-]+)', href)
        if m:
            ui_providers.add(m.group(1))
    print(f"Total distinct providers linked in UI: {len(ui_providers)}")
    print(f"Sample UI providers (first 40): {sorted(list(ui_providers))[:40]}")
    
    # Save the full extracted catalog
    out = {
        "ui_providers_count": len(ui_providers),
        "ui_providers": sorted(list(ui_providers)),
        "all_bundle_slugs_count": len(slugs_found),
        "all_bundle_slugs": sorted(list(slugs_found))
    }
    Path("state/extracted_providers_catalog.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Saved to state/extracted_providers_catalog.json")
