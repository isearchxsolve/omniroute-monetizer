"""Check Local State for app_bound_encrypted_key presence (T11-safe: no values printed)."""
import json, base64, os

LS = r"C:\Users\Admin\AppData\Local\Google\Chrome\User Data\Local State"
print("Local State exists:", os.path.exists(LS))
ls = json.load(open(LS, encoding="utf-8"))
oc = ls.get("os_crypt", {})
print("os_crypt keys:", sorted(oc.keys()))
for k in sorted(oc.keys()):
    v = oc[k]
    if isinstance(v, str):
        try:
            raw = base64.b64decode(v)
            print(f"  {k}: b64_len={len(v)} raw_len={len(raw)} raw_prefix={raw[:6]!r}")
        except Exception as e:
            print(f"  {k}: (not b64) {str(e)[:60]}")
    else:
        print(f"  {k}: type={type(v).__name__}")

# Also check the copied profile's Local State for comparison
for alt in [r"d:\omniroute-chrome-profile-v2\Local State"]:
    if os.path.exists(alt):
        ls2 = json.load(open(alt, encoding="utf-8"))
        oc2 = ls2.get("os_crypt", {})
        print(f"\n{alt}: os_crypt keys = {sorted(oc2.keys())}")
        for k in sorted(oc2.keys()):
            v = oc2[k]
            if isinstance(v, str):
                try:
                    raw = base64.b64decode(v)
                    print(f"  {k}: b64_len={len(v)} raw_len={len(raw)} raw_prefix={raw[:6]!r}")
                except Exception as e:
                    print(f"  {k}: (not b64) {str(e)[:60]}")
