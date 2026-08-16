#!/usr/bin/env python3
"""
Inspect the 295 providers catalog from omniroute_ui_diagnostic/02_providers.json.
"""
import os
import sys
import json
from pathlib import Path

p = Path("omniroute_ui_diagnostic/02_providers.json")
if not p.exists():
    print("02_providers.json not found")
    sys.exit(1)

data = json.loads(p.read_text(encoding="utf-8"))
print(f"Type: {type(data).__name__}")
if isinstance(data, dict):
    print(f"Keys: {list(data.keys())}")
    for k, v in data.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")
            if v and isinstance(v[0], dict):
                print(f"    sample item keys: {list(v[0].keys())}")
        elif isinstance(v, dict):
            print(f"  {k}: {len(v)} keys")
elif isinstance(data, list):
    print(f"List of {len(data)} items")
    if data and isinstance(data[0], dict):
        print(f"Sample item keys: {list(data[0].keys())}")
