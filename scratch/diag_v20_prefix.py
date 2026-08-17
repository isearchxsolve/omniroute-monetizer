"""Own-evidence diagnostic: confirm exact encryption prefix of the 3 target cookies
in the REAL Chrome DB, and thoroughly search the registry for the app-bound key.
Prints only prefixes/lengths — NEVER cookie values (T11)."""
import os
import shutil
import sqlite3
import subprocess
import tempfile

LOCALAPPDATA = os.environ["LOCALAPPDATA"]
CHROME_UD = os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data")

WANT = {
    "chatgpt-web": [("chatgpt.com", "__Secure-next-auth.session-token")],
    "grok-web": [("x.com", "auth_token"), ("grok.com", "auth_token")],
    "zed-hosted": [("zed.dev", "zed.session")],
}

tmp = tempfile.mkdtemp(prefix="diag_")
for prof in ("Default", "Profile 14"):
    src = os.path.join(CHROME_UD, prof, "Network", "Cookies")
    if not os.path.exists(src):
        print(f"[{prof}] no Cookies DB")
        continue
    dst = os.path.join(tmp, prof.replace(" ", "_") + ".db")
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        print(f"[{prof}] copy fail {e}")
        continue
    con = sqlite3.connect(dst)
    cur = con.cursor()
    for slug, specs in WANT.items():
        for dom, name in specs:
            cur.execute(
                "SELECT host_key, name, encrypted_value FROM cookies "
                "WHERE host_key LIKE ? AND (name=? OR name LIKE ?)",
                (f"%{dom}", name, name + ".%"))
            for hk, nm, enc in cur.fetchall():
                prefix = enc[:3].decode("latin1", "replace") if enc else "EMPTY"
                print(f"[{prof}] {slug:14s} {hk} {nm}: prefix={prefix!r} len={len(enc)}")
    con.close()
shutil.rmtree(tmp, ignore_errors=True)

print("\n=== registry search for app_bound_encryption ===")
for hive_key in (
    r"HKLM\SOFTWARE\Google\Chrome",
    r"HKLM\SOFTWARE\WOW6432Node\Google\Chrome",
    r"HKCU\SOFTWARE\Google\Chrome",
):
    r = subprocess.run(["reg", "query", hive_key, "/s"], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if "app_bound" in l.lower() or "encryption" in l.lower()]
    print(f"--- {hive_key}: rc={r.returncode}")
    for l in lines[:10]:
        print("   ", l.strip())
    if not lines and r.returncode == 0:
        print("    (no app_bound/encryption values)")
