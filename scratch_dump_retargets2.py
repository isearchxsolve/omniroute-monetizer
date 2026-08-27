# -*- coding: utf-8 -*-
"""Dump the ACTUAL structure of recorded_exchange for the three chat re-capture targets."""
import json, pathlib

SECRETS = pathlib.Path("state/secrets")
TARGETS = ["session_chatgpt_free_web.json", "session_meta_ai_web.json",
           "session_you_com_chat.json"]

def walk(obj, prefix="", depth=0, max_depth=3):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}: <{type(v).__name__} len={len(v)}>")
                walk(v, prefix + "  ", depth + 1, max_depth)
            else:
                s = str(v)
                print(f"{prefix}{k}: {s[:100]}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            print(f"{prefix}[{i}]:")
            walk(v, prefix + "  ", depth + 1, max_depth)
        if len(obj) > 3:
            print(f"{prefix}... ({len(obj)} total)")

for name in TARGETS:
    p = SECRETS / name
    raw = json.loads(p.read_text(encoding="utf-8"))
    print(f"\n{'='*70}\n== {name} (host={raw.get('host')})")
    rec = raw.get("recorded_exchange")
    if rec is None:
        print("   recorded_exchange: NONE")
        # show top-level keys
        print("   top-level keys:", sorted(raw.keys()))
        continue
    print(f"   recorded_exchange type: {type(rec).__name__}")
    walk(rec)
