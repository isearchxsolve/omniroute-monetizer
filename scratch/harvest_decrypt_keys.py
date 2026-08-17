"""Harvest user's OWN upstream keys from OmniRoute's local encrypted store (Resolution 3).

Decrypts enc:v1:<iv>:<ct>:<tag> api_key fields (AES-256-GCM, scrypt-derived key),
plus plaintext extraApiKeys from providerSpecificData, then verifies each key
against the provider's upstream /models endpoint. Saves verified keys to
state/forest_keys.json (LOCAL ONLY — never logged, per T11).
"""
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import requests

DB = r"C:\Users\Admin\.omniroute\storage.sqlite"
ENV = r"C:\Users\Admin\.omniroute\.env"
OUT = Path(r"d:\omniroute-monetizer\state\forest_keys.json")

# Upstream OpenAI-compatible base URLs per provider (from awesome-freellm-apis + known)
UPSTREAM = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "cerebras": "https://api.cerebras.ai/v1",
    "cohere": "https://api.cohere.com/compatibility/v1",
    "llm7": "https://api.llm7.io/v1",
    "alibaba": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "zai-web": "https://open.bigmodel.cn/api/paas/v4",
    "aion": "https://api.aionlabs.ai/v1",
    "agnes": "https://apihub.agnes-ai.com/v1",
    "opencode-zen": "https://opencode.ai/zen/v1",
    "ainative": "https://api.ainative.ai/v1",
    "nara": None,  # unknown upstream, skip direct verify
    "opencode": None,
    "cloudflare-ai": None,  # account-specific URL
}


def load_enc_key():
    for line in Path(ENV).read_text().splitlines():
        if line.startswith("STORAGE_ENCRYPTION_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("STORAGE_ENCRYPTION_KEY not found")


def derive_keys(secret):
    """Candidate AES keys: current scheme (raw + hex-decoded) and legacy scheme."""
    cands = []
    pw = secret.encode()
    salt = b"omniroute-field-encryption-v1"
    cands.append(hashlib.scrypt(pw, salt=salt, n=16384, r=8, p=1, dklen=32))
    try:
        cands.append(hashlib.scrypt(bytes.fromhex(secret), salt=salt, n=16384, r=8, p=1, dklen=32))
    except ValueError:
        pass
    # legacy: scryptSync(key, sha256(key).slice(0,16), 32)
    legacy_salt = hashlib.sha256(pw).digest()[:16]
    cands.append(hashlib.scrypt(pw, salt=legacy_salt, n=16384, r=8, p=1, dklen=32))
    return cands


def decrypt(field, keys):
    if not field or not field.startswith("enc:v1:"):
        return None
    parts = field.split(":")
    if len(parts) != 5:
        return None
    _, _, iv_h, ct_h, tag_h = parts
    iv, ct, tag = bytes.fromhex(iv_h), bytes.fromhex(ct_h), bytes.fromhex(tag_h)
    for k in keys:
        try:
            return AESGCM(k).decrypt(iv, ct + tag, None).decode()
        except Exception:
            continue
    return None


def verify(provider, key):
    base = UPSTREAM.get(provider)
    if not base:
        return "skip-no-url", 0
    try:
        r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    except Exception as e:
        return f"error:{type(e).__name__}", 0
    if r.status_code != 200:
        return f"http-{r.status_code}", 0
    try:
        data = r.json().get("data", [])
        return "valid", len(data)
    except Exception:
        return "valid-nojson", 0


def main():
    secret = load_enc_key()
    keys = derive_keys(secret)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT provider, api_key, provider_specific_data FROM provider_connections WHERE is_active = 1"
    ).fetchall()
    con.close()

    results = {}
    for provider, api_key, psd_raw in rows:
        entry = {"keys": []}
        if api_key:
            dec = decrypt(api_key, keys)
            if dec:
                entry["keys"].append({"source": "main", "key": dec})
            else:
                entry["decrypt_failed"] = True
        if psd_raw:
            try:
                psd = json.loads(psd_raw)
                for extra in psd.get("extraApiKeys") or []:
                    if isinstance(extra, str) and extra:
                        entry["keys"].append({"source": "extra", "key": extra})
                    elif isinstance(extra, dict) and extra.get("apiKey"):
                        entry["keys"].append({"source": "extra", "key": extra["apiKey"]})
            except Exception:
                pass
        if entry["keys"] or entry.get("decrypt_failed"):
            results[provider] = entry

    print(f"decrypted providers: {sum(1 for e in results.values() if e['keys'])} / {len(results)}")

    # Verify each key against upstream /models
    for provider, entry in results.items():
        for k in entry["keys"]:
            status, n = verify(provider, k["key"])
            k["verify"] = status
            k["models"] = n
            print(f"  {provider} [{k['source']}]: {status} ({n} models)")

    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nsaved -> {OUT}")
    valid = sum(1 for e in results.values() for k in e["keys"] if k.get("verify") == "valid")
    print(f"VERIFIED VALID keys: {valid}")


if __name__ == "__main__":
    main()
