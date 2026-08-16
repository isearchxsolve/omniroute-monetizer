import sqlite3, json

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
uri = "file:" + db.replace("\\", "/") + "?mode=ro"
con = sqlite3.connect(uri, uri=True)
cur = con.cursor()

row = cur.execute(
    "SELECT id, provider, auth_type, is_active, test_status, backoff_level, api_key, access_token, refresh_token, provider_specific_data FROM provider_connections WHERE id=?",
    ("574246f2-1cdf-48ad-83b6-2ca1b541f8e4",),
).fetchone()

if not row:
    print("NOT FOUND")
else:
    cid, prov, at, act, ts, bo, api_key, acc, ref, psd = row
    print("id:", cid)
    print("provider:", prov, "| auth_type:", at, "| is_active:", act, "| test_status:", ts, "| backoff:", bo)
    print("api_key:", (api_key[:60] + "...") if api_key else repr(api_key))
    print("access_token:", (acc[:60] + "...") if acc else repr(acc))
    print("refresh_token:", (ref[:60] + "...") if ref else repr(ref))
    try:
        d = json.loads(psd) if psd else {}
        ek = d.get("extraApiKeys", [])
        print("extraApiKeys count:", len(ek))
        for k in ek:
            print("  extra:", (k[:20] + "...") if isinstance(k, str) else k)
        print("other psd keys:", [k for k in d.keys() if k != "extraApiKeys"])
    except Exception as e:
        print("psd parse err:", e, repr(psd)[:100])

# also: how many connections have enc:v1 api_key?
enc = cur.execute("SELECT COUNT(*) FROM provider_connections WHERE api_key LIKE 'enc:v1:%'").fetchone()[0]
plain = cur.execute("SELECT COUNT(*) FROM provider_connections WHERE api_key IS NOT NULL AND api_key NOT LIKE 'enc:v1:%'").fetchone()[0]
null = cur.execute("SELECT COUNT(*) FROM provider_connections WHERE api_key IS NULL OR api_key=''").fetchone()[0]
print(f"\napi_key stats: enc:v1={enc}, plaintext={plain}, empty/null={null}")

# check the two failing ciphertext prefixes
for prefix in ("enc:v1:631da2bde7c6b6d1b04c87b", "enc:v1:61c3d157e0a08110ec3a7cf"):
    hits = cur.execute("SELECT id, provider, auth_type FROM provider_connections WHERE api_key LIKE ? OR access_token LIKE ? OR refresh_token LIKE ? OR provider_specific_data LIKE ?", (prefix+"%",)*4).fetchall()
    print(f"prefix {prefix}: {hits}")

con.close()
