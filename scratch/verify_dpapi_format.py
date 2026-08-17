"""Verify the DPAPI v10 format by decrypting the existing chat.lm.secret."""
import ctypes
import ctypes.wintypes as wt
import json
import sqlite3

DB = r"C:\Users\Admin\AppData\Roaming\Code\User\globalStorage\state.vscdb"


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


con = sqlite3.connect(DB)
row = con.execute("SELECT value FROM ItemTable WHERE key = 'secret://chat.lm.secret.-2d4b2ee5'").fetchone()
con.close()

buf = json.loads(row[0])["data"]
raw = bytes(buf)
print("prefix:", raw[:3])
for label, candidate in (("full blob", raw), ("after v10", raw[3:])):
    try:
        plain = dpapi_unprotect(candidate)
        print(f"[{label}] OK, decrypted length:", len(plain))
        print(f"[{label}] decrypted (masked):", plain[:10] + b"..." + plain[-6:])
        break
    except OSError as e:
        print(f"[{label}] failed: {e}")
