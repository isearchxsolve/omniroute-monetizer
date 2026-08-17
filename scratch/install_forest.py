"""Install the MODEL FOREST into VS Code Copilot (chatLanguageModels.json + secrets).

Forest = user's OWN harvested upstream keys (verified 200 OK on chat completions):
  NVIDIA x5 keys (102 models each), OpenRouter (414), Alibaba (159),
  Cohere (31), Groq (15), Agnes (7), Cerebras (3).

Excluded after smoke test: opencode-zen (chat 401), llm7 (402 balance),
ainative (connection error), aion (0 models), zai-web/gemini (401).

Reuses the proven v10 AES-GCM secret-store mechanism from install_byok_secrets.py.
Backs up state.vscdb + chatLanguageModels.json first. Idempotent for Forest-* groups.
"""
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from install_byok_secrets import (
    BACKUP_DIR,
    CONFIG,
    STATE_DB,
    buffer_json,
    encrypt_v10,
    get_aes_key,
    make_group,
    new_secret_id,
)

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEYS = Path(r"d:\omniroute-monetizer\state\forest_keys.json")
LISTS = Path(r"d:\omniroute-monetizer\state\forest_model_lists.json")

# Providers verified 200 OK on POST chat/completions with valid payloads
CHAT_URLS = {
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "alibaba": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    "cohere": "https://api.cohere.com/compatibility/v1/chat/completions",
    "agnes": "https://apihub.agnes-ai.com/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
}

PROVIDER_LABELS = {
    "nvidia": "NVIDIA",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "alibaba": "Alibaba",
    "cohere": "Cohere",
    "agnes": "Agnes",
    "cerebras": "Cerebras",
}

# Non-chat model filters (these never work in a chat picker)
EXCLUDE_SUBSTR = (
    "embed", "rerank", "tts", "whisper", "speech", "dall-e", "stable-diffusion",
    "sdxl", "flux", "guard", "moderation", "clip", "bark", "musicgen", "audio",
    "image", "video", "ocr", "paraformer", "sensevoice", "cosyvoice",
)

VISION_SUBSTR = ("-vl", "_vl", "vision", "pixtral", "llava", "qvq", "omni", "gpt-4o", "gemini")


def model_entry(mid: str, url: str) -> dict:
    low = mid.lower()
    return {
        "id": mid,
        "name": mid,
        "url": url,
        "toolCalling": True,
        "vision": any(t in low for t in VISION_SUBSTR),
        "maxInputTokens": 128000,
        "maxOutputTokens": 8192,
    }


def filter_models(models):
    kept = []
    for m in models:
        low = m.lower()
        if any(t in low for t in EXCLUDE_SUBSTR):
            continue
        kept.append(m)
    # dedupe preserving order
    seen = set()
    out = []
    for m in kept:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def main() -> int:
    keys_data = json.loads(KEYS.read_text())
    lists_data = json.loads(LISTS.read_text())

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    aes_key = get_aes_key()
    print("AES key recovered from Local State.")

    # ---- backups
    db_backup = BACKUP_DIR / f"state_vscdb_backup_{stamp}.vscdb"
    src = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(str(db_backup))
    src.backup(dst)
    dst.close()
    src.close()
    print(f"state.vscdb backup: {db_backup}")

    existing_groups = []
    if CONFIG.exists():
        existing_groups = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg_backup = BACKUP_DIR / f"chatLanguageModels_backup_{stamp}.json"
        shutil.copy2(CONFIG, cfg_backup)
        print(f"config backup: {cfg_backup}")

    con = sqlite3.connect(str(STATE_DB), timeout=15)
    con.execute("PRAGMA busy_timeout = 15000")
    cur = con.cursor()
    existing_ids = {
        r[0][len("secret://"):]
        for r in cur.execute(
            "SELECT key FROM ItemTable WHERE key LIKE 'secret://chat.lm.secret.%'"
        )
    }

    # ---- build forest groups
    secrets_to_write = []
    forest_groups = []
    total_models = 0

    for provider, url in CHAT_URLS.items():
        entry = keys_data.get(provider, {})
        valid_keys = [k for k in entry.get("keys", []) if k.get("verify") == "valid"]
        prov_lists = lists_data.get(provider, [])
        label = PROVIDER_LABELS[provider]
        multi = len(valid_keys) > 1
        for ki, k in enumerate(valid_keys):
            # find the fetched model list for this key's index
            src_idx = entry["keys"].index(k)
            models = []
            for pl in prov_lists:
                if pl.get("key_index") == src_idx:
                    models = filter_models(pl.get("models", []))
                    break
            if not models:
                print(f"  {label}[{ki}]: no models, skip")
                continue
            sid = new_secret_id(existing_ids)
            secrets_to_write.append((sid, k["key"]))
            name = f"Forest-{label}-{ki + 1}" if multi else f"Forest-{label}"
            forest_groups.append(make_group(name, sid, [model_entry(m, url) for m in models]))
            total_models += len(models)
            print(f"  {name}: {len(models)} models")

    # ---- assemble final config: keep all non-Forest groups, replace Forest-*
    kept = [g for g in existing_groups if not str(g.get("name", "")).startswith("Forest-")]
    replaced = [g for g in existing_groups if str(g.get("name", "")).startswith("Forest-")]
    if replaced:
        print(f"Replacing {len(replaced)} existing Forest-* group(s).")
    groups = kept + forest_groups
    print(f"Kept {len(kept)} existing group(s): {[g.get('name') for g in kept]}")

    # ---- write secrets
    for sid, plain in secrets_to_write:
        blob = encrypt_v10(aes_key, plain)
        cur.execute(
            "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
            ("secret://" + sid, buffer_json(blob)),
        )
    con.commit()
    print(f"Wrote {len(secrets_to_write)} secrets.")

    # ---- verify round-trip
    ok = True
    for sid, plain in secrets_to_write:
        row = cur.execute(
            "SELECT value FROM ItemTable WHERE key = ?", ("secret://" + sid,)
        ).fetchone()
        raw = bytes(json.loads(row[0])["data"])
        dec = AESGCM(aes_key).decrypt(raw[3:15], raw[15:], None).decode("utf-8")
        if dec != plain:
            ok = False
            print(f"  VERIFY FAIL: {sid}")
    con.close()
    if not ok:
        print("ABORT: secret verification failed, config NOT written.")
        return 1
    print("All secrets verified round-trip.")

    # ---- write config
    CONFIG.write_text(json.dumps(groups, indent=4) + "\n", encoding="utf-8")
    verify = json.loads(CONFIG.read_text(encoding="utf-8"))
    n_models = sum(len(g.get("models", [])) for g in verify)
    print(f"\nchatLanguageModels.json: {len(verify)} groups, {n_models} total models")
    for g in verify:
        print(f"  - {g['name']}: {len(g.get('models', []))}")

    print(
        f"\nFOREST INSTALLED: {total_models} new forest models across "
        f"{len(forest_groups)} groups.\n"
        "FULLY restart VS Code (close ALL windows, reopen) to load the secrets."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
