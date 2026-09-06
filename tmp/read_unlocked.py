import json
import sys
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp_drive import Tab

listing = json.loads(urllib.request.urlopen("http://127.0.0.1:9225/json/list", timeout=20).read())
BODY_JS = "document.body ? document.body.innerText.slice(0, 400) : ''"

for prefix, name in [("8DB27B83", "DIGEN"), ("2675600D", "GIZ"),
                     ("7AF00F90", "QWEN"), ("7510AC85", "POE")]:
    t = next((x for x in listing if x.get("id", "").startswith(prefix)), None)
    if not t:
        print("===", name, "TAB GONE")
        continue
    try:
        tab = Tab(9225, t["id"])
        body = tab.evaluate(BODY_JS)
        tab.close()
        print("===", name, "===")
        print(" ".join(body.split())[:320])
        print()
    except Exception as e:
        print("===", name, "ERROR:", type(e).__name__, str(e)[:150])
