#!/usr/bin/env python3
"""Switch PyGPT global open_router fallback from key1 (now 401) to key2 (live)."""
import json
import os
import shutil
import datetime
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
CONFIG_JSON = os.path.join(WORKDIR, "config.json")
BASE_URL = "https://api.tokenrouter.com/v1"
KEY2 = "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"


def redact(k):
    return k[:6] + "****" + k[-4:]


ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = CONFIG_JSON + ".bak_" + ts
shutil.copy2(CONFIG_JSON, bak)
print("backup:", bak)

with open(CONFIG_JSON, "r", encoding="utf-8") as f:
    cfg = json.load(f)
target = cfg.get("items", cfg) if isinstance(cfg, dict) else cfg
target["api_key_open_router"] = KEY2
target["api_endpoint_open_router"] = BASE_URL
with open(CONFIG_JSON, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)
print("api_key_open_router ->", redact(KEY2))
print("api_endpoint_open_router ->", BASE_URL)
print("DONE")
