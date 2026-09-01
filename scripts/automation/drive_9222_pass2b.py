"""9222 deep-drive pass 2b: targeted re-drive of the 17 remaining NEEDS_DRIVE rows
with longer settles (JS-heavy apps render late), second-attempt reload, and
app-shell detection (empty body + readyState complete + app root div = surface).
Merges verdicts into the v2 ledger."""
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
SHOTS.mkdir(parents=True, exist_ok=True)
LEDGER = ROOT / "state" / "surface_audit_9222_full_v2.json"
OUT = ROOT / "state" / "drive_9222_pass2b.json"
PORT = 9222

SIGNUP_TXT = ("sign up", "create account", "create an account", "get started free",
              "start for free", "try for free", "register")
LOGIN_ONLY_TXT = ("log in to continue", "sign in to continue", "password",
                  "continue with google", "forgot password", "email address")
PAY_TXT = ("credit card", "payment", "billing", "upgrade", "subscription")
CN_LOGIN_TXT = ("登录", "注册", "扫码")


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
        p = SHOTS / f"drive9222p2b_{tag}_{int(time.time())}.png"
        p.write_bytes(base64.b64decode(r["data"]))
        return str(p.relative_to(ROOT))
    except Exception:
        return None


def classify(txt):
    low = (txt or "").lower()
    head = low[:1200]
    cn_head = (txt or "")[:1200]
    if any(h in head for h in PAY_TXT):
        return "PAY_WALL"
    signup = any(h in head for h in SIGNUP_TXT)
    login = any(h in head for h in LOGIN_ONLY_TXT) or "sign in" in head or "log in" in head
    cn_login = any(h in cn_head for h in CN_LOGIN_TXT)
    if signup or cn_login:
        return "SIGNUP_WALL" if signup else "LOGIN_WALL"
    if login:
        return "LOGIN_WALL"
    return None


def page_state(c):
    return c.evaluate(
        "(() => ({rs: document.readyState, "
        "composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
        "[contenteditable=\"\"], div[role=\"textbox\"]'), "
        "appRoot: !!document.querySelector('#root, #__next, #app, [data-reactroot], "
        "main, [role=\"main\"]'), "
        "txt: (document.body ? document.body.innerText : '').slice(0, 1500)}))()",
        timeout=30) or {}


def drive_tab(t, settle=12.0, retry_reload=True):
    url = t.get("url") or ""
    row = {"url": url[:100]}
    wake(t)
    try:
        c = CDP(t["webSocketDebuggerUrl"], timeout=45)
    except Exception as e:
        row["verdict"] = "CDP_FAIL"
        row["detail"] = f"ws-connect {type(e).__name__}"
        return row
    try:
        c.call("Page.enable", timeout=45)
        c.call("Page.navigate", {"url": url}, timeout=45)
        time.sleep(settle)
        st = page_state(c)
        # second attempt with fresh reload for late-rendering apps
        if not st.get("composer") and not (st.get("txt") or "").strip() and retry_reload:
            c.call("Page.navigate", {"url": url}, timeout=45)
            time.sleep(settle)
            st = page_state(c)
        low = (st.get("txt") or "").lower()
        row["readyState"] = st.get("rs")
        row["composer"] = bool(st.get("composer"))
        row["appRoot"] = bool(st.get("appRoot"))
        row["bodyLen"] = len((st.get("txt") or "").strip())
        v = classify(st.get("txt"))
        if row["composer"] and v is None:
            row["verdict"] = "APP_SURFACE"
        elif row["composer"] and v == "PAY_WALL":
            row["verdict"] = "APP_SURFACE"
        elif v:
            row["verdict"] = v
        elif row["appRoot"] and row["bodyLen"] > 0:
            row["verdict"] = "APP_SURFACE"
            row["note"] = "app-shell surface, composer not found at probe instant"
        else:
            row["verdict"] = "NEEDS_DRIVE"
        row["bodyHead"] = low[:160].replace("\n", " | ")
        row["screenshot"] = shot(c, str(t.get("id"))[:8])
    except Exception as e:
        row["verdict"] = "CDP_FAIL"
        row["detail"] = type(e).__name__
        try:
            row["screenshot"] = shot(c, str(t.get("id"))[:8])
        except Exception:
            pass
    finally:
        c.close()
    return row


def devtools_healthy(port, timeout=4.0):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout).read()
        return True
    except Exception:
        return False


def main():
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    queue = [r for r in led["rows"] if r.get("verdict") == "NEEDS_DRIVE"]
    print(f"queue {len(queue)} NEEDS_DRIVE rows", flush=True)

    tabs = [t for t in targets(PORT) if t.get("type") == "page"]
    by_host = {}
    for t in tabs:
        h = (urllib.parse.urlsplit(t.get("url") or "").hostname or "").lower()
        if h and h not in by_host:
            by_host[h] = t

    rows = []
    done = 0
    for lr in queue:
        host = (urllib.parse.urlsplit(lr.get("url") or "").hostname or "").lower()
        t = by_host.get(host)
        if not t:
            r = {"url": lr.get("url"), "verdict": "TAB_GONE"}
        else:
            waited = 0
            while not devtools_healthy(PORT) and waited < 240:
                time.sleep(15)
                waited += 15
            r = drive_tab(t)
        r["pass2b"] = True
        rows.append(r)
        done += 1
        OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"[{done}/{len(queue)}]", r["verdict"].ljust(13),
              (r.get("url") or host)[:60], flush=True)
        time.sleep(3.0)

    merged = 0
    for r in rows:
        if not r.get("url"):
            continue
        pref = r["url"].split("?")[0].rstrip("/")
        for lr2 in led["rows"]:
            if (lr2.get("url") or "").split("?")[0].rstrip("/") == pref:
                for k in ("verdict", "composer", "readyState", "bodyHead",
                          "screenshot", "detail", "appRoot", "bodyLen", "note"):
                    if k in r:
                        lr2[k] = r[k]
                lr2["pass2bAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                merged += 1
                break
    led["pass2bAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(r["verdict"] for r in rows))
    print(f"wrote {OUT}; merged {merged} rows into v2 ledger", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
