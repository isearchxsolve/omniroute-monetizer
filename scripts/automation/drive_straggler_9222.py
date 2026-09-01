"""9222 straggler retry (batch 5): coze renderer-hang and giz /404.

Stronger recovery than batch4: a real Page.navigate reload of the site's chat
surface, longer settle, then the audit-style verdict. Wake-first, paced, one tab
at a time. Output: state/drive_batch5_9222.json; ledger rows merged by url.
"""
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

SHOTS = ROOT / "state" / "surface_audit_evidence"
LEDGER = ROOT / "state" / "surface_audit_9222_full.json"
OUT = ROOT / "state" / "drive_batch5_9222.json"
PORT = 9222
LOGIN_TXT = ("sign in", "sign up", "log in", "continue with google", "create an account")


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
        p = SHOTS / f"drive5_{tag}_{int(time.time())}.png"
        p.write_bytes(base64.b64decode(r["data"]))
        return str(p.relative_to(ROOT))
    except Exception:
        return None


def retry_tab(t, url, settle=12.0):
    row = {"url": url[:100]}
    wake(t)
    try:
        c = CDP(t["webSocketDebuggerUrl"], timeout=30)
        c.call("Page.enable", timeout=30)
        c.call("Page.navigate", {"url": url}, timeout=30)
        time.sleep(settle)
        st = c.evaluate(
            "(() => ({rs: document.readyState, "
            "composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
            "[contenteditable=\"\"], div[role=\"textbox\"]'), "
            "txt: (document.body ? document.body.innerText : '').slice(0, 1200)}))()",
            timeout=30) or {}
        low = (st.get("txt") or "").lower()
        row["readyState"] = st.get("rs")
        row["composer"] = bool(st.get("composer"))
        wall = any(h in low[:400] for h in LOGIN_TXT)
        if row["composer"] and not wall:
            row["verdict"] = "APP_SURFACE"
        elif wall:
            row["verdict"] = "LOGIN_WALL"
        else:
            row["verdict"] = "NEEDS_DRIVE"
        row["bodyHead"] = low[:160].replace("\n", " | ")
        row["screenshot"] = shot(c, str(t.get("id"))[:8])
        c.close()
    except Exception as e:
        row["verdict"] = "CDP_FAIL"
        row["detail"] = type(e).__name__
    return row


def main():
    by_url = {}
    for t in targets(PORT):
        h = (urllib.parse.urlsplit(t.get("url") or "").hostname or "").lower()
        if h and h not in by_url:
            by_url[h] = t

    rows = []
    jobs = [
        ("coze_reload", "www.coze.com", "https://www.coze.com/"),
        ("giz_reload", "www.giz.ai", "https://www.giz.ai/chat"),
    ]
    for tag, host, url in jobs:
        t = by_url.get(host)
        if not t:
            rows.append({"tag": tag, "host": host, "verdict": "TAB_GONE"})
            continue
        r = retry_tab(t, url)
        r["tag"] = tag
        rows.append(r)
        print(tag, "->", r["verdict"], r.get("bodyHead", "")[:90], flush=True)
        time.sleep(4.0)

    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    merged = 0
    for r in rows:
        if not r.get("url"):
            continue
        pref = r["url"].split("?")[0].rstrip("/")
        for lr in led["rows"]:
            if (lr.get("url") or "").split("?")[0].rstrip("/") == pref:
                lr["verdict"] = r["verdict"]
                if r.get("detail"):
                    lr["detail"] = r["detail"]
                if r.get("screenshot"):
                    lr["screenshot"] = r["screenshot"]
                lr["batch5At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                merged += 1
                break
    led["batch5At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")
    print(f"wrote {OUT}; merged {merged} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
