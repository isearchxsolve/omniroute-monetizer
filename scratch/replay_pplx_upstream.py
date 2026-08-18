"""Replay the executor's upstream request with harvested cookies to see the
raw Perplexity SSE response (diagnose empty content)."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
import requests  # noqa: E402

KEYS = os.path.join(os.path.dirname(__file__), "..", "state", "generated_keys.json")
with open(KEYS, "r", encoding="utf-8") as f:
    keys = json.load(f)
entry = keys["cookie_header:perplexity-web"]
cookie_header = entry["cookie_header"] if isinstance(entry, dict) else entry

# Read the executor's buildPplxRequestBody to replicate the payload shape
PROTO = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\open-sse\executors\perplexity-web\protocol.ts"
src = open(PROTO, encoding="utf-8", errors="ignore").read()
i = src.find("buildPplxRequestBody")
print("--- buildPplxRequestBody source (first 2000 chars) ---")
print(src[i:i + 2000])
