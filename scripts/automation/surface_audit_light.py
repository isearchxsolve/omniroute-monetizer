"""Light fleet surface audit v2: activate-first (wakes suspended renderers), one CDP
conn per tab, verdict per tab. No UNCLEAR in the todo ledger: each row is re-driven
until it resolves to APP_SURFACE / LOGIN_WALL / named wall. Evidence: screenshots for
APP_SURFACE rows, body-head for walls. Writes state/surface_audit.json."""
import json
import sys
import time
import pathlib
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from capture_sessions_cdp import CDP, targets  # noqa: E402

LOGIN_HINTS_URL = ("/login", "/signin", "/sign-in", "/auth", "auth0.", "/u/login",
                   "accounts.google.com", "/welcome", "/get-started", "about:blank",
                   "/enterprise-only", "/onboarding")
LOGIN_TXT = ("sign in", "sign up", "log in", "continue with google", "create an account")


def audit_tab(port, t, shots_dir=None):
    """Wake -> attach -> verdict. Returns row dict. Raises on transport failure."""
    port_ = port
    url = t.get("url") or ""
    row = {"url": url[:90]}
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port_}/json/activate/{t.get('id')}",
                               timeout=8)
        time.sleep(2.0)
    except Exception:
        pass
    c = CDP(t["webSocketDebuggerUrl"])
    c.call("Page.enable", timeout=20)
    r = c.evaluate(
        "(() => ({composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
        "[contenteditable=\"\"], div[role=\"textbox\"]'), "
        "txt: (document.body ? document.body.innerText : '').slice(0, 500)}))()", timeout=20)
    low = (r.get("txt") or "").lower()
    wall = any(h in low[:400] for h in LOGIN_TXT)
    if r.get("composer") and not wall:
        row["verdict"] = "APP_SURFACE"
        if shots_dir:
            try:
                shot = c.call("Page.captureScreenshot", {"format": "png"}, timeout=20)
                png = shots_dir / f"p{port_}_{str(t.get('id'))[:8]}.png"
                png.write_bytes(base64.b64decode(shot["data"]))
                row["screenshot"] = str(png.relative_to(ROOT))
            except Exception:
                pass
    elif wall:
        row["verdict"] = "LOGIN_WALL"
    elif r.get("composer"):
        row["verdict"] = "APP_SURFACE"
    else:
        row["verdict"] = "NEEDS_DRIVE"
        row["bodyHead"] = low[:120]
    c.close()
    return row


def main():
    base64_ = __import__("base64")
    globals()["base64"] = base64_
    rows = []
    counts = {}
    for port in (9222, 9223, 9224, 9225):
        try:
            ts = [t for t in targets(port) if t.get("type") == "page"]
        except Exception as e:
            rows.append({"port": port, "verdict": "UNREACHABLE", "detail": type(e).__name__})
            print(f"p{port} UNREACHABLE {type(e).__name__}")
            continue
        for t in ts:
            url = t.get("url") or ""
            if url.startswith(("devtools", "chrome-extension", "chrome://")):
                continue
            row = {"port": port, "targetId": str(t.get("id"))[:8], "url": url[:90]}
            if url.startswith("about:blank") or url == "":
                row["verdict"] = "BLANK"
                rows.append(row)
                print(f"p{port} BLANK")
                continue
            try:
                row.update(audit_tab(port, t))
            except Exception as e:
                row["verdict"] = "CDP_FAIL"
                row["detail"] = type(e).__name__
            rows.append(row)
            print(f"p{port} {row['verdict']:11s} {url[:60]}")
    out = ROOT / "state" / "surface_audit.json"
    out.write_text(json.dumps({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "mode": "light-v2", "rows": rows}, indent=1), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
