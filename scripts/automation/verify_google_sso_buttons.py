#!/usr/bin/env python3
"""Verify Google-SSO button presence on live seat tabs (read-only DOM scan).

Challenge check: the signup executor may emit LOGIN_REQUIRED when its click
selector misses a Google SSO button. This scans the actual live tab DOM for
any Google-SSO affordance so a false LOGIN_REQUIRED can be distinguished from a
genuine no-Google-SSO wall. Read-only: attaches via CDP, evaluates, never
clicks, never navigates, never touches the operator profile (chrome_live_guard).
"""
import json
import sys
import time
import urllib.request
import pathlib
import websocket

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_cdp_safe  # noqa: E402

PORTS = {9222: "providers", 9223: "niloy", 9224: "seat2", 9225: "seat3"}


def targets(port):
    return json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=15).read())


class Tab:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method,
                                  "params": params or {}}))
        import time
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if msg.get("id") == self._id:
                return msg.get("result") or {}
        return {}

    def evaluate(self, expr):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True})
        return str((r.get("result") or {}).get("value") or "")


SCAN_JS = (
    "(() => {"
    " const out = {googleText:false, googleHref:false, labels:[]};"
    " const els = Array.from(document.querySelectorAll('a, button, div[role=button],"
    " [role=link], input[type=button], span'));"
    " for (const el of els) {"
    "  const t = (el.innerText || el.getAttribute('aria-label') || el.title ||"
    "   el.value || '').toLowerCase();"
    "  const h = (el.getAttribute('href') || el.getAttribute('data-href') ||"
    "   (el.onclick ? 'onclick' : '') || '').toLowerCase();"
    "  if (/google/.test(t) || /continue with google|sign in with google|"
    "  sign up with google|use google/.test(t)) { out.googleText = true;"
    "   out.labels.push((el.innerText||'').slice(0,40)); }"
    "  if (/accounts\\.google\\.com|oauth.*google|google.*oauth/.test(h)"
    "   || /client_id=/.test(h) && /google/.test(h)) { out.googleHref = true;"
    "   out.labels.push('href:'+h.slice(0,60)); }"
    " }"
    " // also scan anchors anywhere in markup for google oauth links"
    " const html = document.documentElement.outerHTML.toLowerCase();"
    " if (/accounts\\.google\\.com\\/.*(oauth|signin)/.test(html)) out.googleHref = true;"
    " return JSON.stringify(out);"
    "})()"
)


def wake(port, tid, url):
    # 8.2 recovery: /json/activate re-creates the execution context; if a tab is
    # still discarded, one browser-dispatched Page.navigate to the same URL
    # recovers it. Without this, evaluate() hangs and a real Google button is
    # mis-scanned as absent.
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/activate/{tid}", timeout=8)
    except Exception:
        pass
    time.sleep(1.5)
    try:
        tgt = next((x for x in targets(port)
                    if x.get("id") == tid and x.get("webSocketDebuggerUrl")), None)
        if tgt:
            ws = websocket.create_connection(
                tgt["webSocketDebuggerUrl"], timeout=15,
                max_size=64 * 1024 * 1024)
            try:
                Tab(ws).call("Page.navigate", {"url": url})
            finally:
                ws.close()
    except Exception:
        pass
    time.sleep(3)


def main():
    only_port = int(sys.argv[1]) if len(sys.argv) > 1 else None
    for port, seat in PORTS.items():
        if only_port and port != only_port:
            continue
        assert_cdp_safe(f"http://127.0.0.1:{port}", who="verify_google_sso")
        print(f"=== {seat} ({port}) ===")
        seen = set()
        for t in targets(port):
            if t.get("type") != "page":
                continue
            u = t.get("url", "")
            if u.startswith("chrome") or u in ("about:blank",):
                continue
            if u in seen:
                continue
            seen.add(u)
            host = urllib.parse.urlsplit(u).hostname or u
            ws = None
            try:
                wake(port, t["id"], u)
                ws = websocket.create_connection(
                    t["webSocketDebuggerUrl"], timeout=20,
                    max_size=64 * 1024 * 1024)
                tab = Tab(ws)
                raw = tab.evaluate(SCAN_JS)
                try:
                    res = json.loads(raw)
                except ValueError:
                    res = {"raw": raw[:80]}
                flag = "GOOGLE_SSO" if (res.get("googleText") or
                                        res.get("googleHref")) else "no-google-ss-btn"
                print(f"  {host:42} {flag}  labels={res.get('labels', [])[:3]}")
            except Exception as e:
                print(f"  {host:42} SCAN_ERR {type(e).__name__}")
            finally:
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass


if __name__ == "__main__":
    import urllib.parse  # noqa: E402
    main()
