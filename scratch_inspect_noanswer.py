import json

d = json.load(open(r"d:\omniroute-monetizer\state\selenium_browser_replay.json", encoding="utf-8"))
rows = d.get("results", d if isinstance(d, list) else [])
for r in rows:
    print("===", r.get("host"), "|", r.get("verdict"), "|", r.get("status"))
    for k in ("runFromOrigin", "corsFallback", "corsFallbackOrigin", "corsFallbackError",
              "sendTimeReconstructed", "contentType", "bodyBytes"):
        if k in r:
            print("   ", k, "=", r[k])
    print("    detail:", (r.get("detail", "") or "")[:300])
    bp = r.get("bodyPreview")
    if bp:
        print("    bodyPreview:", bp[:1500].replace("\n", "\\n"))
    print()
