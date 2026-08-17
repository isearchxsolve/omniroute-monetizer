"""Decrypt candidate session cookies straight from the copied Chrome Cookies DBs.
Targets (from shallow sweep): chatgpt-web (chunked next-auth token), grok-web (x.com auth_token),
zed-hosted (zed.session). T11-safe: values NEVER printed; saved to gitignored state/generated_keys.json.
"""
import base64
import json
import os
import shutil
import sqlite3
import tempfile

import win32crypt
from Crypto.Cipher import AES

LOCALAPPDATA = os.environ["LOCALAPPDATA"]
CHROME_UD = os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")

# 1. master key from Local State (DPAPI user scope)
local_state = json.loads(open(os.path.join(CHROME_UD, "Local State"), encoding="utf-8").read())
b64 = local_state["os_crypt"]["encrypted_key"]
raw = base64.b64decode(b64)
assert raw[:5] == b"DPAPI", "unexpected os_crypt prefix"
master_key = win32crypt.CryptUnprotectData(raw[5:], None, None, None, 0)[1]
print(f"master key OK ({len(master_key)} bytes)")


def decrypt_value(enc: bytes):
    if not enc:
        return None, "empty"
    prefix = enc[:3].decode("latin1", "replace")
    if prefix == "v10":
        nonce, ct = enc[3:15], enc[15:]
        try:
            pt = AES.new(master_key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ct[:-16], ct[-16:])
            return pt.decode("utf-8", "replace"), "v10"
        except Exception as e:
            return None, f"v10-decrypt-fail:{type(e).__name__}"
    if prefix == "v20":
        return None, "v20-app-bound (needs Chrome COM, not supported here)"
    # legacy DPAPI-only
    try:
        return win32crypt.CryptUnprotectData(enc, None, None, None, 0)[1].decode("utf-8", "replace"), "dpapi"
    except Exception as e:
        return None, f"legacy-fail:{type(e).__name__}"


# 2. copy DBs
tmpdir = tempfile.mkdtemp(prefix="chrome_dec_")
profiles = {}
for prof in ("Default", "Profile 14"):
    src = os.path.join(CHROME_UD, prof, "Network", "Cookies")
    if os.path.exists(src):
        dst = os.path.join(tmpdir, prof.replace(" ", "_") + ".db")
        shutil.copy2(src, dst)
        profiles[prof] = dst

# 3. extract candidates
WANT = {
    "chatgpt-web": [("chatgpt.com", "__Secure-next-auth.session-token")],  # chunked: .0 .1 ...
    "grok-web": [("x.com", "auth_token"), ("grok.com", "auth_token")],
    "zed-hosted": [("zed.dev", "zed.session")],
}

results = {}
for prof, dbpath in profiles.items():
    con = sqlite3.connect(dbpath)
    cur = con.cursor()
    for slug, specs in WANT.items():
        for dom, name in specs:
            # chunked cookies: name, name.0, name.1 ...
            cur.execute(
                "SELECT host_key, name, encrypted_value, expires_utc FROM cookies "
                "WHERE (host_key LIKE ?) AND (name = ? OR name LIKE ?)",
                (f"%{dom}", name, name + ".%"))
            rows = cur.fetchall()
            if not rows:
                continue
            chunks = {}
            singles = []
            for hk, nm, enc, exp in rows:
                val, how = decrypt_value(enc)
                if val is None:
                    print(f"  [{prof}] {slug} {hk} {nm}: FAILED ({how})")
                    continue
                if nm == name:
                    singles.append((hk, val, exp))
                else:
                    try:
                        idx = int(nm.rsplit(".", 1)[1])
                    except ValueError:
                        continue
                    chunks[idx] = (hk, val, exp)
            if chunks:
                joined = "".join(chunks[i][1] for i in sorted(chunks))
                results.setdefault(slug, []).append(
                    {"profile": prof, "host": chunks[sorted(chunks)[0]][0],
                     "value": joined, "chunks": len(chunks),
                     "expires": chunks[sorted(chunks)[0]][2]})
                print(f"  [{prof}] {slug}: chunked x{len(chunks)} OK, len={len(joined)}")
            for hk, val, exp in singles:
                results.setdefault(slug, []).append(
                    {"profile": prof, "host": hk, "value": val, "chunks": 0, "expires": exp})
                print(f"  [{prof}] {slug}: single OK host={hk} len={len(val)}")
    con.close()

# 4. save (T11: file only, gitignored)
if results:
    store = {}
    if os.path.exists(KEYS_PATH):
        try:
            store = json.loads(open(KEYS_PATH, encoding="utf-8").read())
        except Exception:
            store = {}
    for slug, lst in results.items():
        # prefer Profile 14 (Person 1 = logged-in profile), then freshest expiry
        lst.sort(key=lambda r: (r["profile"] != "Profile 14", -int(r["expires"] or 0)))
        store[f"browser_session:{slug}"] = {
            "value": lst[0]["value"], "profile": lst[0]["profile"],
            "host": lst[0]["host"], "harvested_at": "2026-08-18"}
    json.dump(store, open(KEYS_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nsaved {len(results)} session(s) -> state/generated_keys.json (values masked here)")
else:
    print("\nno decryptable session cookies found")

shutil.rmtree(tmpdir, ignore_errors=True)
