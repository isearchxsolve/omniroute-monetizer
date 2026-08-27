# -*- coding: utf-8 -*-
"""Inspect the digen.ai seat shape (secrets redacted)."""
import json, pathlib

raw = json.loads(pathlib.Path("state/secrets/session_digen_ai.json").read_text(encoding="utf-8"))
print("top keys:", list(raw.keys()))
print("host:", raw.get("host"))
print("modality:", raw.get("modality"))
print("site:", raw.get("site"))
print("status:", json.dumps(raw.get("status")))
print("has recorded_exchange:", bool(raw.get("recorded_exchange")))
print("has recorded_job:", bool(raw.get("recorded_job")))
print("has api:", bool(raw.get("api")))

rj = raw.get("recorded_job")
if isinstance(rj, dict):
    print("recorded_job keys:", list(rj.keys()))
    for k, v in rj.items():
        if isinstance(v, dict):
            print("  ", k, "-> dict keys:", list(v.keys()))
            if "url" in v:
                print("      url:", v.get("url"))
            if "method" in v:
                print("      method:", v.get("method"))
        elif isinstance(v, list):
            print("  ", k, "-> list len", len(v))
        else:
            print("  ", k, "=", str(v)[:80])
