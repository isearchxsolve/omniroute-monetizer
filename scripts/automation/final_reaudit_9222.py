"""Final light re-audit of 9222: confirm every APP_SURFACE ledger row's tab is
still live and still exposes a composer. Readiness probe only - no submits."""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import CDP, targets  # noqa: E402

PORT = 9222


def reg(host):
    parts = (host or "").lstrip(".").lower().split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


led = json.load(open(r"D:\omniroute-monetizer\state\surface_audit_9222_full.json"))
ledger_apps = {}
for r in led["rows"]:
    if r["verdict"] == "APP_SURFACE":
        h = (urllib.parse.urlsplit(r["url"] or "").hostname or "").lower()
        ledger_apps[reg(h)] = r

live = {}
for t in targets(PORT):
    h = (urllib.parse.urlsplit(t.get("url") or "").hostname or "").lower()
    if h:
        live.setdefault(reg(h), t)

gone = [h for h in ledger_apps if h not in live]
print("ledger APP_SURFACE domains not live right now:", gone)

checked = ok = 0
issues = []
for dom, t in sorted(live.items()):
    if dom not in ledger_apps:
        continue
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/activate/{t.get('id')}", timeout=6).read()
    except Exception:
        pass
    time.sleep(1.2)
    try:
        c = CDP(t["webSocketDebuggerUrl"], timeout=20)
        r = c.evaluate(
            "!!document.querySelector('textarea, [contenteditable=\"true\"], "
            "[contenteditable=\"\"], div[role=\"textbox\"]')", timeout=15)
        c.close()
        checked += 1
        if r:
            ok += 1
        else:
            issues.append((dom, "no composer now"))
    except Exception as e:
        issues.append((dom, type(e).__name__))

print(f"checked {checked} live APP_SURFACE tabs; composer still present on {ok}")
for d, v in issues:
    print("ISSUE:", d, v)
