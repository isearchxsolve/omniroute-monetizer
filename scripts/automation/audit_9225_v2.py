"""9225 surface audit v2 (wake-first, post-realign): one CDP conn per tab,
activate first, verdict per tab, screenshot for APP_SURFACE.
Writes state/surface_audit_9225_full.json (v1 ledger is the drained evidence of record)."""
import base64
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from capture_sessions_cdp import CDP, targets  # noqa: E402

PORT = 9225
OUT = ROOT / "state" / "surface_audit_9225_full.json"
SHOTS = ROOT / "state" / "surface_audit_evidence"
SHOTS.mkdir(parents=True, exist_ok=True)

LOGIN_TXT = ("sign in", "sign up", "log in", "continue with google", "create an account")
PAY_TXT = ("credit card", "add a payment method", "payment method")


def main():
    rows = []
    ts = [t for t in targets(PORT) if t.get("type") == "page"]
    for t in ts:
        url = t.get("url") or ""
        if url.startswith(("devtools", "chrome-extension", "chrome://")):
            continue
        row = {"url": url[:100]}
        if url.startswith("about:blank") or url == "":
            row["verdict"] = "BLANK"
            rows.append(row)
            print("BLANK", flush=True)
            continue
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/json/activate/{t.get('id')}", timeout=8).read()
        except Exception:
            pass
        time.sleep(2.5)
        try:
            c = CDP(t["webSocketDebuggerUrl"], timeout=30)
            c.call("Page.enable", timeout=30)
            st = c.evaluate(
                "(() => ({rs: document.readyState, "
                "composer: !!document.querySelector('textarea, [contenteditable=\"true\"], "
                "[contenteditable=\"\"], div[role=\"textbox\"]'), "
                "txt: (document.body ? document.body.innerText : '').slice(0, 1200)}))()",
                timeout=30) or {}
            low = (st.get("txt") or "").lower()
            row["readyState"] = st.get("rs")
            row["composer"] = bool(st.get("composer"))
            wall_txt = any(h in low[:400] for h in LOGIN_TXT)
            pay_txt = any(h in low[:400] for h in PAY_TXT)
            if pay_txt and not row["composer"]:
                row["verdict"] = "PAY_WALL"
            elif row["composer"] and not wall_txt:
                row["verdict"] = "APP_SURFACE"
                try:
                    r = c.call("Page.captureScreenshot", {"format": "png"}, timeout=25)
                    p = SHOTS / f"audit9225_{str(t.get('id'))[:8]}_{int(time.time())}.png"
                    p.write_bytes(base64.b64decode(r["data"]))
                    row["screenshot"] = str(p.relative_to(ROOT))
                except Exception:
                    pass
            elif wall_txt:
                row["verdict"] = "LOGIN_WALL"
            elif row["composer"]:
                row["verdict"] = "APP_SURFACE"
            else:
                row["verdict"] = "NEEDS_DRIVE"
                row["bodyHead"] = low[:140].replace("\n", " | ")
            c.close()
        except Exception as e:
            row["verdict"] = "CDP_FAIL"
            row["detail"] = type(e).__name__
        rows.append(row)
        print(row["verdict"].ljust(13), row["url"][:70], flush=True)
        time.sleep(1.5)

    OUT.write_text(json.dumps(
        {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "port": PORT, "rows": rows}, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(r["verdict"] for r in rows))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

