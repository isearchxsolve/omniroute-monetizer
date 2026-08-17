"""Make the verified local OmniRoute BYOK group the first Copilot choice.

This changes ordering only. It does not alter model IDs, URLs, or secrets.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


CONFIG = Path.home() / "AppData" / "Roaming" / "Code" / "User" / "chatLanguageModels.json"
BACKUP_DIR = Path(r"D:\omniroute-monetizer\state")


def main() -> int:
    groups = json.loads(CONFIG.read_text(encoding="utf-8"))
    omni = [g for g in groups if g.get("name") == "OmniRoute"]
    if len(omni) != 1:
        raise RuntimeError(f"expected exactly one OmniRoute group, found {len(omni)}")
    backup = BACKUP_DIR / f"chatLanguageModels_before_omniroute_default_{datetime.now():%Y%m%d_%H%M%S}.json"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG, backup)
    ordered = omni + [g for g in groups if g.get("name") != "OmniRoute"]
    CONFIG.write_text(json.dumps(ordered, indent=4) + "\n", encoding="utf-8")
    print(f"backup={backup}")
    print(f"groups={len(ordered)} first={ordered[0]['name']} first_model={ordered[0]['models'][0]['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
