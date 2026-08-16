#!/usr/bin/env python3
"""
Inspect allowed provider IDs and custom provider nodes in OmniRoute.
"""
import os
import re
from pathlib import Path

dist_dir = Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks")

found_providers = set()
for f in dist_dir.glob("*.js"):
    text = f.read_text(encoding="utf-8", errors="ignore")
    if "Invalid provider" in text:
        print(f"Found 'Invalid provider' in {f.name}")
        # Extract surrounding context
        idx = text.find("Invalid provider")
        start = max(0, idx - 400)
        end = min(len(text), idx + 400)
        print("Context:\n", text[start:end])
