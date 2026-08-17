"""Shallow sweep: does the user's REAL Chrome have cookies for the 14 NEEDS_BROWSER domains?
Reads each profile's Network/Cookies SQLite DB (copied first to avoid Chrome's lock).
Only checks EXISTENCE (host_key) — never decrypts or prints cookie values (T11)."""
import os
import shutil
import sqlite3
import tempfile

LOCALAPPDATA = os.environ["LOCALAPPDATA"]
CHROME_UD = os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data")
PROFILES = ["Default", "Profile 14", "Profile 16", "Profile 17"]

TARGETS = {
    "adapta-web": ["adapta.one"],
    "blackbox-web": ["blackbox.ai"],
    "chatgpt-web": ["chatgpt.com", "openai.com", "auth0.openai.com"],
    "codebuddy-cn": ["copilot.tencent.com", "tencent.com"],
    "grok-web": ["grok.com", "x.com", "twitter.com"],
    "microsoft-designer-web": ["officeapps.live.com", "live.com", "microsoft.com", "office.com"],
    "muse-spark-web": ["meta.ai", "facebook.com"],
    "perplexity-web": ["perplexity.ai"],
    "suno": ["suno.ai", "suno.com"],
    "t3-web": ["t3.chat"],
    "udio": ["udio.com"],
    "veoaifree-web": ["veoaifree.com"],
    "yuanbao-web": ["yuanbao.tencent.com", "tencent.com"],
    "zed-hosted": ["zed.dev"],
}

tmpdir = tempfile.mkdtemp(prefix="chrome_cookie_scan_")
hits = {}  # slug -> {profile: [host_keys]}

for prof in PROFILES:
    src = os.path.join(CHROME_UD, prof, "Network", "Cookies")
    if not os.path.exists(src):
        src_old = os.path.join(CHROME_UD, prof, "Cookies")
        if os.path.exists(src_old):
            src = src_old
        else:
            print(f"[skip] {prof}: no Cookies DB")
            continue
    dst = os.path.join(tmpdir, prof.replace(" ", "_") + ".db")
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        print(f"[skip] {prof}: copy failed: {e}")
        continue
    try:
        con = sqlite3.connect(dst)
        cur = con.cursor()
        for slug, doms in TARGETS.items():
            for dom in doms:
                cur.execute(
                    "SELECT host_key, name, expires_utc FROM cookies "
                    "WHERE host_key LIKE ? ORDER BY host_key", (f"%{dom}%",))
                rows = cur.fetchall()
                if rows:
                    d = hits.setdefault(slug, {}).setdefault(prof, [])
                    for hk, name, exp in rows:
                        d.append((hk, name, exp))
        con.close()
    except Exception as e:
        print(f"[error] {prof}: {e}")

print("\n=== COOKIE EXISTENCE per NEEDS_BROWSER target ===")
found_any = False
for slug in sorted(TARGETS):
    if slug in hits:
        found_any = True
        for prof, rows in hits[slug].items():
            hosts = sorted({r[0] for r in rows})
            # session-ish cookie names worth flagging (names only, no values)
            names = sorted({r[1] for r in rows})
            print(f"  {slug:26s} [{prof}] {len(rows)} cookies | hosts={hosts}")
            print(f"  {'':26s}  names={names[:15]}")
    else:
        print(f"  {slug:26s} -- no cookies in any profile")

if not found_any:
    print("\nNONE of the 14 targets have cookies in the real Chrome profiles.")

shutil.rmtree(tmpdir, ignore_errors=True)
