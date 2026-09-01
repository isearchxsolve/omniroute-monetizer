"""TRUTH AUDIT: screenshot-first, per-tab signed-in reality for every chat site on
every healthy seat. No verdicts from files - from the live DOM of the actual tabs.
Writes state/surface_audit.json + one screenshot per audited tab."""
import base64
import json
import sys
import time
import pathlib

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from capture_sessions_cdp import CDP, targets, host_of, reg  # noqa: E402

OUT = ROOT / "state" / "surface_audit_evidence"
OUT.mkdir(parents=True, exist_ok=True)

# Login-wall URL hints: if the tab's URL path matches these, it is NOT a signed-in app.
URL_LOGIN_HINTS = ("/login", "/signin", "/sign-in", "/auth", "auth0.", "/session/new",
                   "/u/login", "accounts.google.com", "/welcome", "about:blank")

# DOM login-wall heuristics per host (applied to visible body text).
DOM_LOGIN_TEXTS = ("sign in", "sign up", "log in", "log in to continue",
                   "create an account", "continue with google", "welcome back")


def audit_tab(c, url):
    try:
        body = str(c.evaluate("(document.body ? document.body.innerText : '').slice(0, 4000)") or "")
        low = body.lower()
        has_composer = bool(c.evaluate(
            "!!document.querySelector('textarea, [contenteditable=\"true\"], "
            "[contenteditable=\"\"], div[role=\"textbox\"]')"))
        login_btn = c.evaluate(
            "(() => { const scan = (root) => { for (const b of root.querySelectorAll("
            "'button, a, [role=button]')) { const t = ((b.innerText || '') + ' ' + "
            "(b.getAttribute('aria-label') || '')).toLowerCase(); "
            "if (/sign in|sign up|log in|continue with google/.test(t)) { "
            "const rc = b.getBoundingClientRect(); "
            "if (rc.width > 10) return {label: t.slice(0, 40), "
            "x: Math.round(rc.left + rc.width / 2), "
            "y: Math.round(rc.top + rc.height / 2)}; } } return null; }; "
            "return scan(document); })()")
        verdict = "APP_SURFACE" if (has_composer and not any(h in low[:600] for h in DOM_LOGIN_TEXTS)) \
            else ("LOGIN_WALL" if login_btn else "UNCLEAR")
        return {"verdict": verdict, "hasComposer": has_composer,
                "loginBtn": login_btn, "bodyHead": body[:180].replace("\n", " | ")}
    except Exception as e:
        return {"verdict": "EVAL_ERROR", "detail": f"{type(e).__name__}: {str(e)[:80]}"}


def main():
    rows = []
    for port in (9222, 9223, 9224, 9225):
        try:
            ts = targets(port)
        except Exception as e:
            rows.append({"port": port, "seatReachable": False,
                         "detail": f"{type(e).__name__}"})
            continue
        rows.append({"port": port, "seatReachable": True, "tabCount": len(ts)})
        for t in ts:
            url = t.get("url") or ""
            if url.startswith(("devtools", "chrome://", "about:blank")):
                continue
            row = {"port": port, "targetId": str(t.get("id"))[:8], "url": url[:90]}
            row["urlClass"] = "LOGIN_PATH" if any(h in url.lower() for h in URL_LOGIN_HINTS) else "APP_PATH"
            try:
                c = CDP(t["webSocketDebuggerUrl"])
                c.call("Page.enable")
                c.call("Page.bringToFront", timeout=10)
                time.sleep(0.6)
                info = audit_tab(c, url)
                row.update(info)
                try:
                    shot = c.call("Page.captureScreenshot", {"format": "png"}, timeout=25)
                    png = OUT / f"p{port}_{str(t.get('id'))[:8]}_{host_of(url)[:24]}.png"
                    png.write_bytes(base64.b64decode(shot["data"]))
                    row["screenshot"] = str(png.relative_to(ROOT))
                except Exception:
                    pass
                c.close()
            except Exception as e:
                row["verdict"] = "CDP_FAIL"
                row["detail"] = f"{type(e).__name__}: {str(e)[:60]}"
            rows.append(row)
            print(f"p{port} {row.get('verdict', '?'):11s} {url[:64]}")
    out = ROOT / "state" / "surface_audit.json"
    out.write_text(json.dumps({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "rows": rows}, indent=1), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
