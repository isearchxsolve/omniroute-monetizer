"""Verify Chromium v10 AES-GCM decryption of the existing chat.lm.secret."""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import sqlite3

DB = r"C:\Users\Admin\AppData\Roaming\Code\User\globalStorage\state.vscdb"
LOCAL_STATE = r"C:\Users\Admin\AppData\Roaming\Code\Local State"


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


# 1. Get the AES key from Local State
with open(LOCAL_STATE, "r", encoding="utf-8") as f:
    local_state = json.load(f)
encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
assert encrypted_key[:5] == b"DPAPI", "expected DPAPI prefix"
aes_key = dpapi_unprotect(encrypted_key[5:])
print("AES key length:", len(aes_key))

# 2. Decrypt the existing secret
con = sqlite3.connect(DB)
row = con.execute("SELECT value FROM ItemTable WHERE key = 'secret://chat.lm.secret.-2d4b2ee5'").fetchone()
con.close()
raw = bytes(json.loads(row[0])["data"])
assert raw[:3] == b"v10", "expected v10 prefix"
payload = raw[3:]
nonce = payload[:12]
ciphertext_tag = payload[12:]

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
plain = AESGCM(aes_key).decrypt(nonce, ciphertext_tag, None)
secret = plain.decode("utf-8")
print("decrypted length:", len(secret))
print("decrypted (masked):", secret[:6] + "..." + secret[-4:])
