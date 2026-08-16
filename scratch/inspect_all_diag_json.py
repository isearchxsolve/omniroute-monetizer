#!/usr/bin/env python3
"""
Inspect all diagnostic files in omniroute_ui_diagnostic to list all providers.
"""
import os
import sys
import json
from pathlib import Path

diag_dir = Path("omniroute_ui_diagnostic")

for f in diag_dir.glob("*.json"):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        print(f"File: {f.name} ({type(data).__name__})")
        if isinstance(data, list):
            print(f"  List of {len(data)} items")
            if data and isinstance(data[0], dict):
                print(f"  Sample keys: {list(data[0].keys())}")
        elif isinstance(data, dict):
            print(f"  Dict keys: {list(data.keys())[:10]}")
    except Exception as e:
        print(f"File: {f.name} -> Error: {e}")
