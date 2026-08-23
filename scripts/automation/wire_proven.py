"""Re-probe the proven Reka and OpenAdapter keys upstream, then persist the verdicts.

HISTORY, worth stating plainly: this file used to hold both provider keys as plaintext string
literals, and it was committed and pushed in 9ca01f0 ("LATEST MAAL"). The repository is private,
so the exposure is limited to whoever can read the repo -- but the values are in git history
permanently and the only real remedy is to rotate them at the provider. The literals are gone from
the source now, and the keys are read from state/generated_keys.json, which is gitignored
(.gitignore:3). Nothing here ever prints a key: only fingerprints, per the standing rule that keys
stay masked in all console output and committed artifacts.
"""
from __future__ import annotations
import json
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harvest_free_keys import KEYS_FILE, fingerprint, save_key  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

# Each provider's OWN upstream endpoint -- never OmniRoute. A key counts as working only when the
# provider itself answers, which is why the model call below matters more than /v1/models.
PROVIDERS = {
    "openadapter": {
        "models": "https://api.openadapter.in/v1/models",
        "chat": "https://api.openadapter.in/v1/chat/completions",
        "model": "0G-DeepSeek-V3",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
    },
    "reka": {
        "models": "https://api.reka.ai/v1/models",
        "chat": "https://api.reka.ai/v1/chat/completions",
        "model": "reka-flash",
        "headers": lambda k: {"Authorization": f"Bearer {k}", "X-Api-Key": k},
    },
}


def load_keys() -> dict:
    if not KEYS_FILE.exists():
        print(f"[-] {KEYS_FILE} does not exist -- nothing to re-probe")
        return {}
    return json.loads(KEYS_FILE.read_text(encoding="utf-8"))


def wire_proven() -> int:
    store = load_keys()
    missing = [s for s in PROVIDERS if not store.get(s)]
    if missing:
        print(f"[-] no stored key for: {', '.join(missing)} -- mint one with "
              f"replay.py --only {','.join(missing)}")

    for slug, cfg in PROVIDERS.items():
        key = store.get(slug)
        if not key:
            continue
        print(f"\n[*] {slug}: probing upstream with {fingerprint(key)}")
        try:
            r = requests.get(cfg["models"], headers=cfg["headers"](key), timeout=15)
        except Exception as exc:
            print(f"    GET /v1/models failed: {type(exc).__name__}")
            continue
        print(f"    GET /v1/models: HTTP {r.status_code}")
        if r.status_code != 200:
            continue

        # 200 on /v1/models only proves the key authenticates. together's key did exactly that and
        # then returned 402 on every completion, so the completion is the part that decides.
        cr = requests.post(cfg["chat"], headers=cfg["headers"](key),
                           json={"model": cfg["model"],
                                 "messages": [{"role": "user", "content": "Respond with 'OK'"}],
                                 "max_tokens": 128},
                           timeout=30)
        text = ""
        if cr.status_code == 200:
            try:
                text = (cr.json()["choices"][0]["message"].get("content") or "").strip()
            except Exception:
                text = ""
        print(f"    POST /v1/chat/completions: HTTP {cr.status_code} | {text[:80]!r}")
        if cr.status_code == 200 and text:
            save_key(slug, key, True, f"Proven 200 OK with real text on {cfg['model']}")
            print(f"[+] {slug}: PROVEN upstream, verdict saved")
        else:
            print(f"[-] {slug}: authenticated but produced no text -- NOT counted as proven")
    return 0


if __name__ == "__main__":
    raise SystemExit(wire_proven())
