"""Install TokenRouter + OmniRoute BYOK models into VS Code Copilot.

VS Code 1.133 stable reads BYOK config from:
  %APPDATA%/Code/User/chatLanguageModels.json   (vendor "customendpoint")

The vendor schema marks `apiKey` as secret:true, so the resolver
(_resolveConfiguration in extensionHostProcess.js) ONLY accepts secret
references of the form ${input:chat.lm.secret.<id>} and looks them up in
the secret storage. Raw apiKey strings are silently dropped (that is why
the models never appeared).

Secret storage = %APPDATA%/Code/User/globalStorage/state.vscdb, ItemTable,
key = "secret://chat.lm.secret.<id>", value = JSON {"type":"Buffer","data":[...]}
where the bytes are Chromium v10 format: b"v10" + 12-byte nonce + AES-256-GCM
ciphertext+tag, encrypted with the key from %APPDATA%/Code/Local State
(os_crypt.encrypted_key, DPAPI-wrapped).

Verified this session by decrypting the pre-existing entry successfully.

NOTE: The running VS Code caches state.vscdb in memory, so a FULL restart of
VS Code (close all windows, reopen) is required after this script runs.
"""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import random
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CODE_DIR = Path.home() / "AppData" / "Roaming" / "Code"
USER_DIR = CODE_DIR / "User"
CONFIG = USER_DIR / "chatLanguageModels.json"
STATE_DB = USER_DIR / "globalStorage" / "state.vscdb"
LOCAL_STATE = CODE_DIR / "Local State"
BACKUP_DIR = Path(r"d:\omniroute-monetizer\state")

SECRET_PREFIX = "chat.lm.secret."

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


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi_unprotect(data: bytes) -> bytes:
    blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed: {ctypes.GetLastError()}")
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return out


def get_aes_key() -> bytes:
    local_state = json.loads(LOCAL_STATE.read_text(encoding="utf-8"))
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    assert encrypted_key[:5] == b"DPAPI", "expected DPAPI prefix in Local State key"
    key = dpapi_unprotect(encrypted_key[5:])
    assert len(key) == 32, f"expected 32-byte AES key, got {len(key)}"
    return key


def encrypt_v10(aes_key: bytes, plaintext: str) -> bytes:
    nonce = random.randbytes(12)
    ct = AESGCM(aes_key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return b"v10" + nonce + ct


def buffer_json(blob: bytes) -> str:
    # Node Buffer JSON serialization used by VS Code
    return json.dumps({"type": "Buffer", "data": list(blob)}, separators=(",", ":"))


def new_secret_id(existing: set) -> str:
    # Mimic VS Code: SECRET_KEY_PREFIX + int32.toString(16) (may start with '-')
    while True:
        n = ctypes.c_int32(random.getrandbits(32)).value
        sid = SECRET_PREFIX + format(n, "x")
        if sid not in existing:
            existing.add(sid)
            return sid


def make_group(name: str, secret_id: str, models: list) -> dict:
    return {
        "name": name,
        "vendor": "customendpoint",
        "apiKey": "${input:" + secret_id + "}",
        "apiType": "chat-completions",
        "models": models,
    }


def tokenrouter_model(label: str) -> dict:
    return {
        "id": MODEL_ID,
        "name": f"qwen3.8-max-free ({label})",
        "url": URL,
        "toolCalling": True,
        "vision": False,
        "maxInputTokens": 128000,
        "maxOutputTokens": 16000,
    }


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    aes_key = get_aes_key()
    print("AES key recovered from Local State (DPAPI-unwrapped).")

    # ---- backup state.vscdb via SQLite online backup API (safe while VS Code runs)
    db_backup = BACKUP_DIR / f"state_vscdb_backup_{stamp}.vscdb"
    src = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(str(db_backup))
    src.backup(dst)
    dst.close()
    src.close()
    print(f"state.vscdb backup: {db_backup}")

    # ---- backup chatLanguageModels.json
    existing_groups = []
    if CONFIG.exists():
        existing_groups = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg_backup = BACKUP_DIR / f"chatLanguageModels_backup_{stamp}.json"
        shutil.copy2(CONFIG, cfg_backup)
        print(f"chatLanguageModels.json backup: {cfg_backup}")

    # ---- open DB for writing (busy timeout in case VS Code holds a write lock)
    con = sqlite3.connect(str(STATE_DB), timeout=15)
    con.execute("PRAGMA busy_timeout = 15000")
    cur = con.cursor()

    existing_ids = {
        r[0][len("secret://"):]
        for r in cur.execute(
            "SELECT key FROM ItemTable WHERE key LIKE 'secret://chat.lm.secret.%'"
        )
    }
    print(f"Existing secret ids: {sorted(existing_ids)}")

    # Remove any secrets we installed on a previous run (idempotency).
    # We cannot know old ids, so we replace groups by name and orphan old
    # secrets only if they are ours; instead we keep them (harmless).

    secrets_to_write = []  # (secret_id, plaintext_key)
    groups = []

    # keep pre-existing groups that we do not manage
    managed_prefixes = ("TokenRouter-", "OmniRoute")
    kept = [g for g in existing_groups if not str(g.get("name", "")).startswith(managed_prefixes)]
    print(f"Kept pre-existing group(s): {[g.get('name') for g in kept]}")
    groups.extend(kept)

    for label, key in LIVE_KEYS:
        sid = new_secret_id(existing_ids)
        secrets_to_write.append((sid, key))
        groups.append(make_group(f"TokenRouter-{label}", sid, [tokenrouter_model(label)]))

    omni_sid = new_secret_id(existing_ids)
    secrets_to_write.append((omni_sid, OMNIROUTE_KEY))
    groups.append(
        make_group(
            "OmniRoute",
            omni_sid,
            [
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
        )
    )

    # ---- write secrets
    for sid, plain in secrets_to_write:
        blob = encrypt_v10(aes_key, plain)
        cur.execute(
            "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
            ("secret://" + sid, buffer_json(blob)),
        )
    con.commit()
    print(f"Wrote {len(secrets_to_write)} secrets into state.vscdb.")

    # ---- verify each secret round-trips
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
        else:
            print(f"  verified: {sid} -> {plain[:6]}...{plain[-4:]}")
    con.close()
    if not ok:
        print("ABORT: secret verification failed, chatLanguageModels.json NOT written.")
        return 1

    # ---- write chatLanguageModels.json
    CONFIG.write_text(json.dumps(groups, indent=4) + "\n", encoding="utf-8")
    verify = json.loads(CONFIG.read_text(encoding="utf-8"))
    print(f"\nchatLanguageModels.json now has {len(verify)} group(s):")
    for g in verify:
        print(f"  - {g['name']}: {len(g['models'])} model(s), apiKey={g['apiKey'][:30]}...")

    print(
        "\nDONE. Now FULLY restart VS Code (close ALL windows, then reopen).\n"
        "A window reload is NOT enough - the secret store is cached in memory.\n"
        "After restart, open Chat -> model picker and you should see:\n"
        "  qwen3.8-max-free (key2) ... (key7)  +  7 OmniRoute models."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
