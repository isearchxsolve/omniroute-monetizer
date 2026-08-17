#!/usr/bin/env python3
"""
Configure PyGPT (pygpt-net) with 7 TokenRouter routes, each bound to a distinct
API key, all targeting model qwen/qwen3.8-max-free at https://api.tokenrouter.com/v1.

Design (evidence-based, from py-gpt source):
- The `open_router` provider implements llama_index mode and reads per-model
  `llama_index.args` for api_key / api_base / model (open_router.py llama()).
  This is the ONLY path that supports per-model (multi-key) overrides.
- Chat mode resolves keys from GLOBAL config (models.py prepare_client_args),
  so we also set api_key_open_router + api_endpoint_open_router as a fallback
  (chat mode will use key #1).
- get_openrouter_model() passes the model id through unchanged (only appends
  ":online" if web-search remote tool is enabled, which we do not enable).

Backup-first. No secrets printed to stdout (keys redacted in logs).
"""
import json
import os
import shutil
import sys
import datetime

WORKDIR = os.path.join(os.path.expanduser("~"), ".config", "pygpt-net")
MODELS_JSON = os.path.join(WORKDIR, "models.json")
CONFIG_JSON = os.path.join(WORKDIR, "config.json")

BASE_URL = "https://api.tokenrouter.com/v1"
MODEL_ID = "qwen/qwen3.8-max-free"

# 7 verified-working TokenRouter keys (all returned 200 OK on /models + /chat/completions).
KEYS = [
    "sk-vpHUXIq5GyO9YQipqHgBHERF24SOCseXocFjjxfG5cY685iL",
    "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE",
    "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",
    "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",
    "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg",
    "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu",
    "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc",
]


def redact(k):
    return k[:6] + "****" + k[-4:] if k and len(k) > 12 else "****"


def backup(path):
    if not os.path.exists(path):
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path + ".bak_" + ts
    shutil.copy2(path, dst)
    return dst


def build_entry(idx, key):
    mid = "tokenrouter-qwen38max-key{}".format(idx + 1)
    return mid, {
        "id": mid,
        "name": "TokenRouter qwen3.8-max-free (key {})".format(idx + 1),
        "mode": ["llama_index", "agent", "agent_llama", "expert"],
        "llama_index": {
            "args": [
                {"name": "model", "value": MODEL_ID, "type": "str"},
                {"name": "api_key", "value": key, "type": "str"},
                {"name": "api_base", "value": BASE_URL, "type": "str"},
            ],
            "env": [],
        },
        "ctx": 32768,
        "tokens": 4096,
        "default": False,
        "input": ["text"],
        "output": ["text"],
        "extra": {},
        "imported": False,
        "provider": "open_router",
        "tool_calls": True,
    }


def main():
    print("WORKDIR:", WORKDIR)
    if not os.path.isdir(WORKDIR):
        print("ERROR: config dir does not exist yet. Run pygpt once to generate defaults first.")
        sys.exit(2)
    if not os.path.exists(MODELS_JSON):
        print("ERROR: models.json not found. Run pygpt once to generate defaults first.")
        sys.exit(2)

    # ---- models.json ----
    b1 = backup(MODELS_JSON)
    print("models.json backup:", b1)
    with open(MODELS_JSON, "r", encoding="utf-8") as f:
        models = json.load(f)
    items = models.setdefault("items", {})
    added, updated = 0, 0
    for i, key in enumerate(KEYS):
        mid, entry = build_entry(i, key)
        if mid in items:
            updated += 1
        else:
            added += 1
        items[mid] = entry
        print("  route {}: {} -> key {}".format(i + 1, mid, redact(key)))
    with open(MODELS_JSON, "w", encoding="utf-8") as f:
        json.dump(models, f, indent=4, ensure_ascii=False)
    print("models.json: added={}, updated={}, total_items={}".format(added, updated, len(items)))

    # ---- config.json (global fallback for chat mode) ----
    if os.path.exists(CONFIG_JSON):
        b2 = backup(CONFIG_JSON)
        print("config.json backup:", b2)
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # config.json may store values as {"__meta__":..., "items": {...}} or flat dict.
        target = cfg.get("items", cfg) if isinstance(cfg, dict) else cfg
        target["api_key_open_router"] = KEYS[0]
        target["api_endpoint_open_router"] = BASE_URL
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        print("config.json: api_key_open_router={} , api_endpoint_open_router={}".format(
            redact(KEYS[0]), BASE_URL))
    else:
        print("WARN: config.json not found; skipped global fallback (chat mode will need a key).")

    print("DONE")


if __name__ == "__main__":
    main()
