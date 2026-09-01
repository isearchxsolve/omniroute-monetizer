"""9224 deep-drive: resolve NEEDS_DRIVE / CDP_FAIL rows via reload + classify.
One tab at a time, wake-first, paced, screenshots for evidence. Walls named.
Output: state/drive_9224_pass1.json; ledger updated in place."""
import base64
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from capture_sessions_cdp import CDP, targets  # noqa: E402

PORT = 9224
OUT = ROOT / "state" / "drive_9224_pass1.json"
LEDGER = ROOT / "state" / "surface_audit_9224_full.json"
SHOTS = ROOT / "state" / "surface_audit_evidence"

LOGIN_TXT = ("sign in", "sign up", "log in", "continue with google", "create an account")
PAY_TXT = ("credit card", "add a payment method", "payment method", "pricing")
HOME_TXT = ("©", "privacy policy", "terms of service", "all rights reserved",
            "cookie policy")


def wake(t):
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/activate/{t.get('id')}", timeout=8).read()
    except Exception:
        pass
    time.sleep(2.5)


def shot(c, tag):
    try:
        r = c.call("Page.captureScreenshot", {"format": "png"}, timeout=25)
        p = SHOTS / f"drive9224_{tag}_{int(time.time())}.png"
        p.write_bytes(base64.b64decode(r["data"]))
        return str(p.relative_to(ROOT))
    except Exception:
        return None


def classify(low, composer):
    head = low[:500]
    if any(h in head for h in PAY_TXT) and not composer:
        return "PAY_WALL"
    wall = any(h in head for h in LOGIN_TXT)
    if composer and not wall:
        return "APP_SURFACE"
    if wall:
        return "LOGIN_WALL"
    if composer:
        return "APP_SURFACE"
    home = any(h in low[:900] for h in HOME_TXT)
    if home:
        return "SITE_HOME"
    return "NEEDS_DRIVE"


def drive(t, tag):
    url = t.get("url") or ""
    row = {"url": url[:110]}
    wake(t)
    try:
        c = CDP(t["webSocketDebuggerUrl"], timeout=30)
        c.call("Page.enable", timeout=30)
        c.call("Page.navigate", {"url": url}, timeout=30)
        time.sleep(10.0)
        st = c.evaluate(
            "(() => ({rs: document.readyState, "
            "composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
            "[contenteditable=\"\"], div[role=\"textbox\"]'), "
            "txt: (document.body ? document.body.innerText : '').slice(0, 1200)}))()",
            timeout=30) or {}
        low = (st.get("txt") or "").lower()
        row["readyState"] = st.get("rs")
        row["composer"] = bool(st.get("composer"))
        row["verdict"] = classify(low, row["composer"])
        row["bodyHead"] = low[:160].replace("\n", " | ")
        if row["verdict"] == "APP_SURFACE":
            row["screenshot"] = shot(c, str(t.get("id"))[:8])
        c.close()
    except Exception as e:
        row["verdict"] = "CDP_FAIL"
        row["detail"] = type(e).__name__
        row["screenshot"] = None
    return row


def main():
    by_url = {}
    for t in targets(PORT):
        h = (urllib.parse.urlsplit(t.get("url") or "").hostname or "").lower()
        if h and h not in by_url:
            by_url[h] = t

    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    queue = []
    for r in led["rows"]:
        if r["verdict"] in ("NEEDS_DRIVE", "CDP_FAIL"):
            h = (urllib.parse.urlsplit(r.get("url") or "").hostname or "").lower()
            if h and h in by_url:
                queue.append((h, by_url[h]))
    print(f"queue: {len(queue)} tabs", flush=True)

    results = []
    for i, (h, t) in enumerate(queue):
        tag = str(t.get("id"))[:8]
        r = drive(t, tag)
        results.append(r)
        print(f"{i+1}/{len(queue)}", h, "->", r["verdict"], flush=True)
        time.sleep(3.0)
        OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")

    merged = 0
    for r in results:
        pref = (r.get("url") or "").split("?")[0].rstrip("/")
        for lr in led["rows"]:
            if (lr.get("url") or "").split("?")[0].rstrip("/") == pref:
                if r["verdict"] in ("CDP_FAIL",) and lr["verdict"] not in ("CDP_FAIL",):
                    continue
                lr["verdict"] = r["verdict"]
                if r.get("detail"):
                    lr["detail"] = r["detail"]
                if r.get("screenshot"):
                    lr["screenshot"] = r["screenshot"]
                lr["pass1At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                merged += 1
                break
    led["pass1At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(r["verdict"] for r in results))
    print(f"merged {merged} rows into ledger", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
