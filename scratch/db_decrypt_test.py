import sqlite3, os, base64, json

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
uri = "file:" + db.replace("\\", "/") + "?mode=ro"
con = sqlite3.connect(uri, uri=True)
cur = con.cursor()

print("=== db_meta keys ===")
for k, v in cur.execute("SELECT key, value FROM db_meta"):
    vs = str(v)
    print(f"{k}: {vs[:80]}{'...' if len(vs)>80 else ''}")

# env file key
envp = r"C:\Users\Admin\.omniroute\.env"
envkey = None
if os.path.exists(envp):
    for line in open(envp, encoding="utf-8", errors="ignore"):
        if line.startswith("STORAGE_ENCRYPTION_KEY"):
            envkey = line.split("=", 1)[1].strip().strip('"').strip("'")
print("\nenv STORAGE_ENCRYPTION_KEY present:", bool(envkey), "len:", len(envkey) if envkey else 0)

# try to decrypt nvidia api_key with AES-256-GCM
row = cur.execute("SELECT api_key FROM provider_connections WHERE id=?", ("574246f2-1cdf-48ad-83b6-2ca1b541f8e4",)).fetchone()
ct_full = row[0]
print("\nnvidia api_key ciphertext:", ct_full[:70] + "...")

def try_decrypt(key_material, ct_full):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    # format guess: enc:v1:<iv_hex>:<ciphertext+tag_hex>
    parts = ct_full.split(":")
    # enc : v1 : iv : data
    iv_hex = parts[2]
    data_hex = ":".join(parts[3:])
    iv = bytes.fromhex(iv_hex)
    data = bytes.fromhex(data_hex)
    # derive 32-byte key
    import hashlib
    if len(key_material) == 64:
        try:
            key = bytes.fromhex(key_material)
        except Exception:
            key = hashlib.sha256(key_material.encode()).digest()
    elif len(key_material) == 32:
        key = key_material.encode()
    else:
        key = hashlib.sha256(key_material.encode()).digest()
    aes = AESGCM(key)
    pt = aes.decrypt(iv, data, None)
    return pt.decode()

if envkey:
    try:
        pt = try_decrypt(envkey, ct_full)
        print("DECRYPT OK with env key! plaintext starts:", pt[:12] + "...")
    except Exception as e:
        print("DECRYPT FAILED with env key:", type(e).__name__, e)

con.close()
