import json
import time

P = r"D:\omniroute-monetizer\state\surface_audit_9225_full.json"
led = json.loads(open(P, encoding="utf-8-sig").read())
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
merged = 0
for r in led["rows"]:
    u = r.get("url", "")
    if "digen.ai" in u:
        r["verdict"] = "APP_SURFACE"
        r["detail"] = ("operator manual sign-in verified: signed-in workspace, "
                       "150 daily credits deposited (CDP text evidence 2026-09-02)")
        r["ssoSweepAt"] = now
        merged += 1
    elif "giz.ai" in u:
        r["verdict"] = "APP_SURFACE"
        r["detail"] = ("operator manual sign-in verified: /chat 404 gone, signed-in "
                       "workspace visible (Kunal Das, Free plan) - SURFACE_GONE_404 superseded")
        r["ssoSweepAt"] = now
        merged += 1
tmp = P + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(led, f, indent=1, ensure_ascii=False)
import os
os.replace(tmp, P)
print(f"merged {merged} rows with full detail fields")
from collections import Counter
print(Counter(r["verdict"] for r in led["rows"]))
