"""Write the real BYOK config: chatLanguageModels.json with 6 TokenRouter key groups.

Root cause of "models not showing": github.copilot.chat.customEndpoints in
settings.json is NOT read by VS Code 1.133 stable. The real BYOK mechanism is
%APPDATA%/Code/User/chatLanguageModels.json (vendor "customendpoint").

Verified in extensionHostProcess.js: model identifier = vendor/group/id, so
6 groups each serving the same model id get 6 DISTINCT picker entries.
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

USER_DIR = Path.home() / "AppData" / "Roaming" / "Code" / "User"
CONFIG = USER_DIR / "chatLanguageModels.json"
BACKUP_DIR = Path(r"d:\omniroute-monetizer\state")

# Live keys verified 200 OK this session (key1 REVOKED - excluded)
LIVE_KEYS = [
    ("key2", "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"),
    ("key3", "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN"),
    ("key4", "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU"),
    ("key5", "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg"),
    ("key6", "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu"),
    ("key7", "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc"),
]

MODEL_ID = "qwen/qwen3.8-max-free"
URL = "https://api.tokenrouter.com/v1/chat/completions"

# OmniRoute local router (key copied from the old non-functional customEndpoints setting)
OMNIROUTE_KEY = "sk-2daf4dd6d1e45047-5d97a4-eb7e8d3b"
OMNIROUTE_URL = "http://localhost:20128/v1/chat/completions"
OMNIROUTE_MODELS = [
    "auto/best-coding",
    "auto/best-reasoning",
    "auto/best-chat",
    "frontier",
    "fusion-coder",
    "kimi-coding",
    "moonshotai/kimi-k3-free",
]


def make_group(label: str, key: str) -> dict:
    return {
        "name": f"TokenRouter-{label}",
        "vendor": "customendpoint",
        "apiKey": key,
        "apiType": "chat-completions",
        "models": [
            {
                "id": MODEL_ID,
                "name": f"qwen3.8-max-free ({label})",
                "url": URL,
                "toolCalling": True,
                "vision": False,
                "maxInputTokens": 128000,
                "maxOutputTokens": 16000,
            }
        ],
    }


def make_omniroute_group() -> dict:
    return {
        "name": "OmniRoute",
        "vendor": "customendpoint",
        "apiKey": OMNIROUTE_KEY,
        "apiType": "chat-completions",
        "models": [
            {
                "id": m,
                "name": m,
                "url": OMNIROUTE_URL,
                "toolCalling": True,
                "vision": False,
                "maxInputTokens": 128000,
                "maxOutputTokens": 16000,
            }
            for m in OMNIROUTE_MODELS
        ],
    }


def main() -> int:
    existing = []
    if CONFIG.exists():
        existing = json.loads(CONFIG.read_text(encoding="utf-8"))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"chatLanguageModels_backup_{stamp}.json"
        shutil.copy2(CONFIG, backup)
        print(f"Backup written: {backup}")

    # Keep any non-TokenRouter groups (e.g. the pre-existing "Custom Endpoint 2")
    kept = [g for g in existing if not str(g.get("name", "")).startswith("TokenRouter-")]
    print(f"Kept {len(kept)} pre-existing group(s): {[g.get('name') for g in kept]}")

    groups = kept + [make_group(label, key) for label, key in LIVE_KEYS]
    CONFIG.write_text(json.dumps(groups, indent=4) + "\n", encoding="utf-8")

    # Verify round-trip
    verify = json.loads(CONFIG.read_text(encoding="utf-8"))
    print(f"\nVerification: {len(verify)} groups in chatLanguageModels.json:")
    for g in verify:
        m = g["models"][0]
        print(f"  - {g['name']}: {m['id']} -> {m['url']}")
    print("\nDone. Reload VS Code (or run 'Developer: Reload Window') to see the models.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
