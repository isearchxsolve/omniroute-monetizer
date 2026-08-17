"""Add TokenRouter multi-key endpoints to VS Code Copilot customEndpoints.

Backs up settings.json first, preserves the existing OmniRoute entry,
and adds one endpoint entry per live TokenRouter key (keys 2-7).
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SETTINGS = Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json"
BACKUP_DIR = Path(r"d:\omniroute-monetizer\state")

# Live keys verified 200 OK this session (key1 is REVOKED - excluded)
LIVE_KEYS = [
    ("key2", "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"),
    ("key3", "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN"),
    ("key4", "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU"),
    ("key5", "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg"),
    ("key6", "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu"),
    ("key7", "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc"),
]

URL = "https://api.tokenrouter.com/v1"
MODEL = "qwen/qwen3.8-max-free"


def main() -> int:
    raw = SETTINGS.read_text(encoding="utf-8")
    settings = json.loads(raw)

    # Backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"vscode_settings_backup_{stamp}.json"
    shutil.copy2(SETTINGS, backup)
    print(f"Backup written: {backup}")

    endpoints = settings.get("github.copilot.chat.customEndpoints")
    if not isinstance(endpoints, list):
        endpoints = []
        settings["github.copilot.chat.customEndpoints"] = endpoints

    existing_names = {e.get("name") for e in endpoints if isinstance(e, dict)}
    added = 0
    for label, key in LIVE_KEYS:
        name = f"TokenRouter-{label}"
        if name in existing_names:
            print(f"skip (exists): {name}")
            continue
        endpoints.append({
            "name": name,
            "url": URL,
            "type": "openai",
            "apiKey": key,
            "models": [MODEL],
        })
        existing_names.add(name)
        added += 1
        print(f"added: {name}")

    SETTINGS.write_text(json.dumps(settings, indent=4) + "\n", encoding="utf-8")

    # Verify round-trip
    verify = json.loads(SETTINGS.read_text(encoding="utf-8"))
    eps = verify["github.copilot.chat.customEndpoints"]
    print(f"\nVerification: {len(eps)} endpoints in file:")
    for e in eps:
        print(f"  - {e['name']} -> {e['url']} ({len(e['models'])} model(s))")
    print(f"\nDone. Added {added} TokenRouter endpoints, OmniRoute preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
