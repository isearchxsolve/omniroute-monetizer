"""APPEND OmniRoute combo model IDs to ZCode's EXISTING omniroute provider entries.
- Keeps ALL existing settings/models/apiKeys untouched (append-only).
- Verifies each entry's existing apiKey against OmniRoute; reports dead ones (no overwrite).
- Backup-first. Idempotent (skips models already present).
"""
import json, shutil, sys, time
from datetime import datetime

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
ZCODE_CFG = r"C:\Users\Admin\.zcode\v2\config.json"
from oauth_keepalive import resolve_password

def verify_key(key):
    body = {"model": "auto/best-coding",
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 8, "stream": False}
    try:
        r = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=90,
                          headers={"Authorization": f"Bearer {key}"})
        return r.status_code
    except Exception as e:
        return f"ERR {type(e).__name__}"

# ---- 2. backup ----
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = rf"d:\omniroute-monetizer\state\zcode_config_backup_{ts}.json"
shutil.copy2(ZCODE_CFG, bak)
print(f"BACKUP -> {bak}")

# ---- 3. append combo models to existing omniroute entries ----
with open(ZCODE_CFG, encoding="utf-8") as f:
    cfg = json.load(f)

COMBOS = [
    "auto/best-coding", "auto/best-reasoning", "auto/best-chat",
    "frontier", "kimi-coding", "fusion-coder",
    "auto/pro-coding", "auto/pro-reasoning", "auto/pro-chat",
    "Frontier Max", "auto/asian-flagships", "auto/free-chat",
    "moonshotai/kimi-k3-free",
]

def model_entry():
    return {
        "limit": {"context": 200000, "output": 32000},
        "modalities": {"input": ["text"], "output": ["text"]},
        "zcode": {"modified": True},
    }

touched = []
for pid, prov in cfg.get("provider", {}).items():
    if str(prov.get("name", "")).lower() != "omniroute":
        continue
    key = prov.get("options", {}).get("apiKey", "")
    kstat = verify_key(key) if key else "NO KEY"
    models = prov.setdefault("models", {})
    added = [m for m in COMBOS if m not in models]
    for m in added:
        models[m] = model_entry()
    touched.append((pid, kstat, added, len(models)))

with open(ZCODE_CFG, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"\nWROTE {ZCODE_CFG}")
for pid, kstat, added, total in touched:
    print(f"\n  provider {pid}:")
    print(f"    existing apiKey verify -> {kstat}")
    print(f"    appended {len(added)} models: {added}")
    print(f"    total models now: {total}")

# ---- 4. validate ----
cfg2 = json.load(open(ZCODE_CFG, encoding="utf-8"))
print("\nJSON valid: True")
print("total providers:", len(cfg2.get("provider", {})))
