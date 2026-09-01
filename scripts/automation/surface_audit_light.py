"""Light fleet surface audit: one CDP conn per tab, quick evaluate, no bringToFront,
no screenshots. Writes state/surface_audit.json (full rows) + prints the verdict table."""
import json
import sys
import time
import pathlib

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from capture_sessions_cdp import CDP, targets  # noqa: E402

LOGIN_HINTS_URL = ("/login", "/signin", "/sign-in", "/auth", "auth0.", "/u/login",
                   "accounts.google.com", "/welcome", "/get-started", "about:blank",
                   "/enterprise-only", "/onboarding")

rows = []
for port in (9222, 9223, 9224, 9225):
    try:
        ts = targets(port)
    except Exception as e:
        rows.append({"port": port, "verdict": "UNREACHABLE", "detail": type(e).__name__})
        print(f"p{port} UNREACHABLE {type(e).__name__}")
        continue
    for t in ts:
        url = t.get("url") or ""
        tid = str(t.get("id"))[:8]
        if url.startswith(("devtools", "chrome-extension", "chrome://")):
            continue
        row = {"port": port, "targetId": tid, "url": url[:90]}
        if url.startswith("about:blank") or url == "":
            row["verdict"] = "BLANK"
            rows.append(row)
            print(f"p{port} BLANK      (about:blank)")
            continue
        row["urlClass"] = "LOGIN_PATH" if any(h in url.lower() for h in LOGIN_HINTS_URL) else "APP_PATH"
        try:
            c = CDP(t["webSocketDebuggerUrl"])
            c.call("Page.enable", timeout=8)
            r = c.evaluate(
                "(() => ({composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
                "[contenteditable=\"\"], div[role=\"textbox\"]'), "
                "txt: (document.body ? document.body.innerText : '').slice(0, 500)}))()", timeout=10)
            c.close()
            low = (r.get("txt") or "").lower()
            head = low[:400]
            wall_txt = any(h in head for h in ("sign in", "sign up", "log in",
                                               "continue with google", "create an account"))
            if r.get("composer") and not wall_txt:
                row["verdict"] = "APP_SURFACE"
            elif wall_txt:
                row["verdict"] = "LOGIN_WALL"
            elif r.get("composer"):
                row["verdict"] = "APP_SURFACE"
            else:
                row["verdict"] = "UNCLEAR"
            row["bodyHead"] = low[:120]
        except Exception as e:
            row["verdict"] = "CDP_FAIL"
            row["detail"] = type(e).__name__
        rows.append(row)
        print(f"p{port} {row['verdict']:11s} {url[:64]}")

out = ROOT / "state" / "surface_audit.json"
out.write_text(json.dumps({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "mode": "light", "rows": rows}, indent=1), encoding="utf-8")
print("wrote", out)
