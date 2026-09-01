"""9222 resume drive (batch 4): the remaining non-terminal ledger rows.

Scope (from the graded ledger state/surface_audit_9222_full.json):
  - coze.com        CDP_FAIL retry (renderer hang)        -> wake-first re-drive
  - giz.ai          TAB_GONE, tab reopened at /404        -> navigate to /chat, re-drive
  - yi.baichuan-ai  TAB_GONE, tab reopened at root        -> navigate to /chat, re-drive
  - rtst.ai         API-credential seat, CDP UI bypassed by design (worklog #1151)
                    -> recorded, not driven
  - LOGIN_WALL rows (creen, akool, chatgpt, pollinations, magichour, hailuoai)
                    -> signup-vs-login classification, screenshot + wall text head

Rules honoured: wake-first (activate + settle + 30s timeouts) because renderer
suspension is the proven CDP_FAIL root cause; paced sequential single-tab work;
walls are reported, never solved; no credentials typed anywhere.
Output: state/drive_batch4_9222.json, ledger rows merged into
state/surface_audit_9222_full.json (matched by url prefix), screenshots in
state/surface_audit_evidence/.
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
SHOTS.mkdir(parents=True, exist_ok=True)
LEDGER = ROOT / "state" / "surface_audit_9222_full.json"
OUT = ROOT / "state" / "drive_batch4_9222.json"
PORT = 9222

SIGNUP_TXT = ("sign up", "create account", "create an account", "get started free",
              "start for free", "try for free", "register")
LOGIN_ONLY_TXT = ("log in to continue", "sign in to continue", "password",
                  "continue with google", "forgot password", "email address")
PAY_TXT = ("credit card", "payment", "billing", "upgrade", "subscription")
ONBOARD_TXT = ("tell us about", "about you", "your name", "what brings you")


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
        p = SHOTS / f"drive4_{tag}_{int(time.time())}.png"
        p.write_bytes(base64.b64decode(r["data"]))
        return str(p.relative_to(ROOT))
    except Exception:
        return None


def classify(txt):
    low = (txt or "").lower()
    head = low[:1200]
    if any(h in head for h in PAY_TXT):
        return "PAY_WALL", low
    if any(h in head for h in ONBOARD_TXT):
        return "ONBOARDING_WALL", low
    signup = any(h in head for h in SIGNUP_TXT)
    login = any(h in head for h in LOGIN_ONLY_TXT) or "sign in" in head or "log in" in head
    if signup and not login:
        return "SIGNUP_WALL", low
    if signup and login:
        return "SIGNUP_WALL", low
    if login:
        return "LOGIN_WALL", low
    return None, low


def page_state(c):
    return c.evaluate(
        "(() => ({rs: document.readyState, "
        "composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
        "[contenteditable=\"\"], div[role=\"textbox\"]'), "
        "txt: (document.body ? document.body.innerText : '').slice(0, 1500)}))()",
        timeout=30) or {}


def drive_tab(t, navigate_to=None, settle=6.0):
    """Wake -> (optional navigate) -> read surface -> verdict row."""
    url = t.get("url") or ""
    row = {"url": url[:100]}
    wake(t)
    c = CDP(t["webSocketDebuggerUrl"], timeout=30)
    try:
        c.call("Page.enable", timeout=30)
        if navigate_to:
            c.call("Page.navigate", {"url": navigate_to}, timeout=30)
            time.sleep(settle)
        st = page_state(c)
        row["readyState"] = st.get("rs")
        row["composer"] = bool(st.get("composer"))
        v, low = classify(st.get("txt"))
        if row["composer"] and v is None:
            row["verdict"] = "APP_SURFACE"
        else:
            row["verdict"] = v or "NEEDS_DRIVE"
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


def main():
    by_url = {}
    for t in targets(PORT):
        h = (urllib.parse.urlsplit(t.get("url") or "").hostname or "").lower()
        if h and h not in by_url:
            by_url[h] = t

    rows = []

    # --- non-terminal rows needing a re-drive -------------------------------
    jobs = [
        ("coze_retry", "www.coze.com", None),
        ("giz_reopen", "www.giz.ai", "https://www.giz.ai/chat"),
        ("baichuan_reopen", "yi.baichuan-ai.com", "https://yi.baichuan-ai.com/chat"),
    ]
    for tag, host, nav in jobs:
        t = by_url.get(host)
        if not t:
            rows.append({"tag": tag, "host": host, "verdict": "TAB_GONE"})
            continue
        r = drive_tab(t, navigate_to=nav)
        r["tag"] = tag
        rows.append(r)
        print(tag, "->", r["verdict"], flush=True)
        time.sleep(3.0)

    # --- rtst: API-credential seat, CDP UI bypass by design ------------------
    rows.append({"tag": "rtst_by_design", "host": "rtst.ai",
                 "verdict": "API_SEAT_BYPASS_UI",
                 "detail": "rtst served via API-credential seat (RtstApiClient, JWT); "
                           "CDP UI driving bypassed by design (worklog #1151)"})
    print("rtst -> API_SEAT_BYPASS_UI (by design)", flush=True)

    # --- LOGIN_WALL signup-vs-login checks -----------------------------------
    walls = ["www.creen.ai", "www.akool.com", "chatgpt.com",
             "pollinations.ai", "magichour.ai", "hailuoai.com"]
    for host in walls:
        t = by_url.get(host)
        if not t:
            rows.append({"tag": "wall_check", "host": host, "verdict": "TAB_GONE"})
            continue
        r = drive_tab(t)
        r["tag"] = "wall_check"
        rows.append(r)
        print("wall", host, "->", r["verdict"], flush=True)
        time.sleep(3.0)

    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    # --- merge into the graded ledger (match by url prefix) ------------------
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
                lr["batch4At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                merged += 1
                break
    led["batch4At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")
    print(f"wrote {OUT}; merged {merged} rows into ledger", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
