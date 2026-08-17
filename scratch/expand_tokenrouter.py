"""Expand TokenRouter-key2..key7 groups to TokenRouter's FULL chat catalog.

The 6 live keys (separate accounts) currently expose only qwen3.8-max-free each.
TokenRouter /models returns 125 models. This script:
1. Verifies each key's /models access (200 OK).
2. Filters to chat-capable models (drops image/video/audio/embedding).
3. Rewrites each TokenRouter-keyN group with the full catalog, reusing the
   EXISTING secret references (keys already in state.vscdb — no new secrets).
Backs up chatLanguageModels.json first.
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests

CONFIG = Path.home() / "AppData" / "Roaming" / "Code" / "User" / "chatLanguageModels.json"
BACKUP_DIR = Path(r"d:\omniroute-monetizer\state")
CATALOG = Path(r"d:\omniroute-monetizer\state\tokenrouter_models.json")
URL = "https://api.tokenrouter.com/v1/chat/completions"

# live keys for per-account /models verification (key1 revoked, excluded)
KEYS = {
    "TokenRouter-key2": "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE",
    "TokenRouter-key3": "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",
    "TokenRouter-key4": "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",
    "TokenRouter-key5": "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg",
    "TokenRouter-key6": "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu",
    "TokenRouter-key7": "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc",
}

EXCLUDE_SUBSTR = (
    "seedream", "kling", "dreamina", "happyhorse", "t2v", "-image", "image-",
    "embedding", "audio", "voxtral", "mai-image", "gpt-5-image", "seedance",
)

VISION_SUBSTR = ("-vl", "_vl", "vision", "omni", "gpt-4o", "gemini", "glm-4.6v", "mimo-v2-omni")


def is_chat(mid: str) -> bool:
    low = mid.lower()
    return not any(t in low for t in EXCLUDE_SUBSTR)


def model_entry(mid: str) -> dict:
    low = mid.lower()
    return {
        "id": mid,
        "name": mid,
        "url": URL,
        "toolCalling": True,
        "vision": any(t in low for t in VISION_SUBSTR),
        "maxInputTokens": 128000,
        "maxOutputTokens": 16000,
    }


def main() -> int:
    catalog = json.loads(CATALOG.read_text())
    chat_models = [m for m in catalog if is_chat(m)]
    print(f"catalog: {len(catalog)} -> chat-capable: {len(chat_models)}")

    # verify each account can list models
    live = []
    for name, key in KEYS.items():
        try:
            r = requests.get(
                "https://api.tokenrouter.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=45,
            )
            n = len(r.json().get("data", [])) if r.status_code == 200 else 0
            print(f"  {name}: {r.status_code} ({n} models)")
            if r.status_code == 200:
                live.append(name)
        except Exception as e:
            print(f"  {name}: ERROR {type(e).__name__}")

    if not live:
        print("ABORT: no live TokenRouter keys")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cfg_backup = BACKUP_DIR / f"chatLanguageModels_backup_{stamp}.json"
    shutil.copy2(CONFIG, cfg_backup)
    print(f"config backup: {cfg_backup}")

    groups = json.loads(CONFIG.read_text(encoding="utf-8"))
    expanded = 0
    for g in groups:
        name = g.get("name", "")
        if name in live:
            g["models"] = [model_entry(m) for m in chat_models]
            expanded += 1
            print(f"  expanded {name}: {len(chat_models)} models (secret ref kept: {g['apiKey'][:35]}...)")

    CONFIG.write_text(json.dumps(groups, indent=4) + "\n", encoding="utf-8")
    verify = json.loads(CONFIG.read_text(encoding="utf-8"))
    total = sum(len(g.get("models", [])) for g in verify)
    print(f"\nchatLanguageModels.json: {len(verify)} groups, {total} total models")
    print("FULLY restart VS Code (close ALL windows) to pick up the expanded picker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
