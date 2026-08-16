import sqlite3, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
import hashlib

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
envp = r"C:\Users\Admin\.omniroute\.env"

envkey = None
for line in open(envp, encoding="utf-8", errors="ignore"):
    if line.startswith("STORAGE_ENCRYPTION_KEY"):
        envkey = line.split("=", 1)[1].strip().strip('"').strip("'")
print("env key len:", len(envkey))

def derive_current(k):
    return Scrypt(salt=b"omniroute-field-encryption-v1", length=32, n=16384, r=8, p=1).derive(k.encode())

def derive_legacy(k):
    salt = hashlib.sha256(k.encode()).digest()[:16]
    return Scrypt(salt=salt, length=32, n=16384, r=8, p=1).derive(k.encode())

def try_decrypt(key32, val):
    body = val[len("enc:v1:"):]
    parts = body.split(":")
    if len(parts) != 3:
        return None, f"malformed parts={len(parts)}"
    iv, ct, tag = bytes.fromhex(parts[0]), bytes.fromhex(parts[1]), bytes.fromhex(parts[2])
    try:
        pt = AESGCM(key32).decrypt(iv, ct + tag, None)
        return pt.decode(), None
    except Exception as e:
        return None, type(e).__name__

con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
cur = con.cursor()

kc = derive_current(envkey)
kl = derive_legacy(envkey)

rows = cur.execute("SELECT id, provider, auth_type, api_key, access_token, refresh_token FROM provider_connections WHERE api_key LIKE 'enc:v1:%' OR access_token LIKE 'enc:v1:%' OR refresh_token LIKE 'enc:v1:%'").fetchall()
print(f"\n{len(rows)} connections with encrypted fields")
ok_c = ok_l = fail = 0
for cid, prov, at, ak, acc, ref in rows:
    results = []
    for fname, val in (("api_key", ak), ("access_token", acc), ("refresh_token", ref)):
        if not val or not val.startswith("enc:v1:"):
            continue
        pt, err = try_decrypt(kc, val)
        if pt is not None:
            results.append(f"{fname}:CURRENT-OK({pt[:8]}...)")
            ok_c += 1
            continue
        pt2, err2 = try_decrypt(kl, val)
        if pt2 is not None:
            results.append(f"{fname}:LEGACY-OK({pt2[:8]}...)")
            ok_l += 1
            continue
        results.append(f"{fname}:FAIL({err}/{err2})")
        fail += 1
    print(f"{prov:20s} {at:8s} {cid[:8]} | " + "; ".join(results))

print(f"\nSUMMARY: current-key-ok={ok_c}, legacy-key-ok={ok_l}, fail={fail}")
con.close()
