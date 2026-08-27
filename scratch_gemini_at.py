import json, sys, re
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

with Page("gemini.google.com", port=9222) as p:
    # 1. WIZ_global_data.at
    try:
        at = p.evaluate("(window.WIZ_global_data && window.WIZ_global_data.at) || null")
        print("WIZ at:", repr(at[:40]) if at else None)
    except Exception as e:
        print("at eval err:", e); at = None
    # 2. FdrFJe (session id used in f.sid?) and SNlM0e
    for key in ["FdrFJe", "SNlM0e", "cfb2h"]:
        try:
            v = p.evaluate(f"(window.WIZ_global_data && window.WIZ_global_data['{key}']) || null")
            print(f"WIZ {key}:", repr(v[:60]) if isinstance(v, str) else v)
        except Exception:
            pass
    # 3. current f.sid from location or AF_initDataCallback
    try:
        href = p.evaluate("location.href")
        print("href:", href)
    except Exception:
        pass
    # 4. Look for fsid in page data
    try:
        fsid = p.evaluate("""(() => {
            const m = document.documentElement.innerHTML.match(/"([-]{0,1}\\d{16,})"\\s*,\\s*null\\s*,\\s*"aid"/);
            return m ? m[1] : null;
        })()""")
        print("fsid regex:", fsid)
    except Exception as e:
        print("fsid err:", e)
    # 5. cookies for at cookie
    r = p.send("Network.getAllCookies")
    for c in r.get("cookies", []):
        if c["name"] in ("OSID",) or c["name"].startswith("at") or c["name"] == "COMPASS":
            pass
    # check for 'at' in cookies
    names = [c["name"] for c in r.get("cookies", []) if "google.com" in c.get("domain","")]
    print("google.com cookie names:", names)
