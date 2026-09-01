#!/usr/bin/env python3
"""cdp_drive.py -- primitive executor for agent-driven fleet automation.

DELIBERATE ARCHITECTURE (operator directive, 2026-08-31): this file contains
NO decision-making. It executes one primitive per invocation and returns JSON
evidence. The calling agent reads the evidence and decides the next primitive.
The `sso` subcommand replays ONLY the proven bounded Google-SSO playbook
(site SSO button -> google -> chooser -> consent, one click each) and stops at
any wall. It never types, never bypasses CAPTCHA/MFA/quota/payment, never
claims signup/graduation/capacity, and emits only canonical signup_classify
labels (or WALL / NO_GOOGLE_BUTTON / ALREADY_SIGNED_IN).

    python cdp_drive.py targets --port 9223 [--contains groq]
    python cdp_drive.py probe  --port 9223 --tid <full-id>
    python cdp_drive.py read   --port 9223 --tid <id> [--max 700]
    python cdp_drive.py click  --port 9223 --tid <id> --js google|vercel|chooser|continue
    python cdp_drive.py nav    --port 9223 --tid <id> --url https://...
    python cdp_drive.py shot   --port 9223 --tid <id> --name foo.png
    python cdp_drive.py cookies --port 9223 --tid <id> --url https://host
    python cdp_drive.py sso    --port 9223 --tid <id> --url <site-url> [--budget 300]
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tab_graduation_sweep import assert_automation_seat, tab_targets  # noqa: E402
from signup_classify import (  # noqa: E402
    body_is_hard_wall, classify_final_provider_state, classify_pre_sso_surface)

EVID = pathlib.Path(__file__).resolve().parents[2] / "state" / "tab_harness_evidence"
BODY_JS = "document.body ? document.body.innerText.slice(0, %d) : ''"


class Tab:
    def __init__(self, port, tid, timeout=25):
        listing = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=20).read())
        mine = next((t for t in listing
                     if t.get("id") == tid and t.get("webSocketDebuggerUrl")), None)
        if mine is None:
            raise RuntimeError(f"target {tid[:12]} has no debugger url on :{port}")
        self.ws_port = port
        self._connect(mine["webSocketDebuggerUrl"], timeout)

    def _connect(self, url, timeout):
        import websocket
        self.ws = websocket.create_connection(url, timeout=timeout, max_size=64 * 1024 * 1024)
        self._id = 0

    def call(self, method, params=None):
        from websocket import WebSocketTimeoutException
        self._id += 1
        want = self._id
        self.ws.send(json.dumps({"id": want, "method": method, "params": params or {}}))
        deadline = time.monotonic() + getattr(self, "call_deadline", 30)
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.monotonic()))
            try:
                msg = json.loads(self.ws.recv())
            except WebSocketTimeoutException:
                continue  # idle socket: keep waiting until deadline
            if msg.get("id") == want:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result") or {}
        raise RuntimeError(f"{method} timed out")

    def evaluate(self, expr):
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return str((res.get("result") or {}).get("value") or "")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def out(doc):
    print(json.dumps(doc, indent=1, ensure_ascii=False))
    return 0


CLICK_JS = {
    "google": (
        "(() => { const c = Array.from(document.querySelectorAll("
        "'button, a, [role=\"button\"]'));"
        "const g = c.find(el => {"
        " const s = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')"
        " + ' ' + (el.getAttribute('href') || '')).toLowerCase();"
        " return (/continue with google|sign in with google|sign up with google|"
        "log ?in with google|login with google/i.test(s)); });"
        "if (!g) return 'none'; g.click();"
        "return 'clicked:' + (g.innerText || '').slice(0, 40); })()"),
    "vercel": (
        "(() => { const c = Array.from(document.querySelectorAll("
        "'button, a, [role=\"button\"]'));"
        "const v = c.find(el => {"
        " const s = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')"
        " + ' ' + (el.getAttribute('href') || '')).toLowerCase();"
        " return /sign in with vercel/i.test(s); });"
        "if (!v) return 'none'; v.click();"
        "return 'clicked:' + (v.innerText || '').slice(0, 40); })()"),
    "chooser": (
        "(() => { const a = document.querySelector('[data-identifier]');"
        "if (!a) return 'none'; a.click();"
        "return 'clicked:' + (a.getAttribute('data-identifier') || 'account'); })()"),
    "continue": (
        "(() => { const b = Array.from(document.querySelectorAll("
        "'button, div[role=\"button\"]'))"
        ".find(el => /^(continue|allow|i agree)$/i.test((el.innerText || '').trim()));"
        "if (!b) return 'none'; b.click(); return 'consent-clicked'; })()"),
    "gate": (
        "(() => { const c = Array.from(document.querySelectorAll('button, a'));"
        "const hit = c.find(el => (/^(log ?in|log ?in to continue|sign ?in|sign ?up|"
        "sign ?in to continue)$/i.test((el.innerText || '').trim()))"
        " && (el.offsetParent !== null || el.getClientRects().length > 0));"
        "if (!hit) return 'none'; hit.click();"
        "return 'gate:' + (hit.innerText || '').trim().slice(0, 30); })()"),
}


def poll_url(port, tid, seconds):
    end = time.monotonic() + seconds
    last = ""
    while time.monotonic() < end:
        time.sleep(2)
        listing = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=20).read())
        t = next((x for x in listing if x.get("id") == tid), None)
        url = (t or {}).get("url") or ""
        if url and url == last:
            return url
        last = url
    return last


def read_surface(port, tid, max_chars=500):
    tab = Tab(port, tid)
    try:
        body = tab.evaluate(BODY_JS % max_chars)
        url = tab.evaluate("location.origin + location.pathname")
    finally:
        tab.close()
    return url, body


def cmd_targets(a):
    owner = assert_automation_seat(a.port)
    rows = [t for t in tab_targets(owner)
            if a.contains in (t.get("url") or "").lower()]
    return out([{"id": t["id"], "url": (t.get("url") or "")[:120]} for t in rows])


def cmd_probe(a):
    Tab(a.port, a.tid).close()
    listing = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{a.port}/json/list", timeout=20).read())
    t = next((x for x in listing if x.get("id") == a.tid), None)
    url = (t or {}).get("url") or ""
    probe = probe_state(a.port, a.tid, wake_url=url)
    probe["targetUrl"] = url
    return out(probe)


def cmd_read(a):
    url, body = read_surface(a.port, a.tid, a.max)
    return out({"url": url, "body": body.replace("\n", " | ")[:a.max]})


def cmd_click(a):
    tab = Tab(a.port, tid)
    try:
        r = tab.evaluate(CLICK_JS[a.js])
    finally:
        tab.close()
    return out({"click": a.js, "result": r})


def cmd_nav(a):
    tab = Tab(a.port, tid)
    try:
        tab.call("Page.navigate", {"url": a.url})
    finally:
        tab.close()
    url = poll_url(a.port, a.tid, 20)
    return out({"navigated": url})


def cmd_shot(a):
    tab = Tab(a.port, a.tid)
    try:
        data = tab.call("Page.captureScreenshot", {"format": "png"}).get("data")
    finally:
        tab.close()
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / a.name).write_bytes(base64.b64decode(data))
    return out({"shot": a.name})


FIND_JS = (
    "(() => { const c = Array.from(document.querySelectorAll('button, a, "
    "div[role=\"button\"]'))"
    ".filter(el => /sign|log|google|github|vercel|auth/i.test("
    "(el.innerText || '') + ' ' + (el.getAttribute('href') || ''))"
    " && (el.offsetParent !== null || el.getClientRects().length > 0))"
    ".slice(0, 12).map(el => ({tag: el.tagName,"
    " t: (el.innerText || '').trim().slice(0, 32),"
    " href: (el.getAttribute('href') || '').slice(0, 70)}));"
    "return JSON.stringify(c); })()"
)


def cmd_find(a):
    tab = Tab(a.port, a.tid)
    try:
        r = tab.evaluate(FIND_JS)
        u = tab.evaluate("location.origin + location.pathname")
    finally:
        tab.close()
    return out({"url": u, "controls": r})


def cmd_cookies(a):
    tab = Tab(a.port, a.tid)
    try:
        res = tab.call("Network.getCookies", {"urls": [a.url]})
    finally:
        tab.close()
    names = sorted({c.get("name", "") for c in res.get("cookies", [])})
    auth = [n for n in names if any(k in n.lower()
            for k in ("token", "session", "auth", "jwt", "sid"))]
    return out({"cookieNames": names, "authLike": auth})


def cmd_sso(a):
    """Bounded Google-SSO playbook. Decisions that matter are still the
    agent's: this executes the proven happy path and STOPS at anything unusual,
    returning evidence for the agent to handle."""
    steps, t0 = [], time.monotonic()
    src_host = _host(a.url)
    tid = resolve_tid(a.port, src_host, a.tid, None)
    steps.append(f"src {src_host} tid {tid[:8]}")

    def budget_left():
        return a.budget - (time.monotonic() - t0)

    # 1. probe current surface
    r = probe_state(a.port, tid, wake_url=a.url)
    if not r.get("signedOut"):
        ev, body, url = _evidence(a.port, tid, src_host)
        pre = classify_pre_sso_surface(url, body, bool(ev))
        return out({"state": "ALREADY_SIGNED_IN" if pre == "LOGIN_REQUIRED" else pre,
                    "finalUrl": url, "steps": steps})

    # 2. up to 5 bounded clicks: site gate -> site-SSO / google / chooser / consent
    clicked = {"google": False, "vercel": False, "chooser": False, "continue": False,
               "gate": False}
    google_seen = False
    state = None
    for round_i in range(6):
        if budget_left() <= 10:
            state = "WALL"
            steps.append("budget exhausted")
            break
        tid = resolve_tid(a.port, src_host, tid, None)
        listing = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{a.port}/json/list", timeout=20).read())
        t = next((x for x in listing if x.get("id") == tid), None)
        url = (t or {}).get("url") or ""
        host = _host(url)
        steps.append(f"surface {host} {url[:80]}")

        if "accounts.google.com" in host:
            google_seen = True
            path = (urllib.parse.urlsplit(url).path or "").lower()
            if "chooser" in path or "oauthchooseaccount" in path:
                if clicked["chooser"]:
                    state = "SSO_INITIATED"
                    break
                r = _click(a.port, tid, "chooser")
                clicked["chooser"] = True
                steps.append(f"chooser {r}")
                if r == "none":
                    state = "SSO_INITIATED"
                    break
                poll_url(a.port, tid, min(30, budget_left()))
                continue
            if "challenge" in path or "otp" in path:
                state = "WALL"
                steps.append("google OTP/MFA challenge - never handled")
                break
            if "signin/consent" in path or "oauthapprove" in path or "/signin/oauth" in path:
                r = _click(a.port, tid, "continue")
                steps.append(f"consent {r}")
                poll_url(a.port, tid, min(30, budget_left()))
                continue
            if "/v3/signin" in path or "password" in path:
                state = "WALL"
                steps.append("google password/interactive surface - never typed")
                break
            poll_url(a.port, tid, min(15, budget_left()))
            continue

        # non-google surface: read it
        surf_url, body = read_surface(a.port, tid, 800)
        low = body.lower()
        if body_is_hard_wall(low):
            state = "WALL"
            steps.append("hard wall on provider surface")
            break
        has_google = any(s in low for s in
                         ("continue with google", "sign in with google", "sign up with google"))
        if has_google and not clicked["google"]:
            r = _click(a.port, tid, "google")
            clicked["google"] = True
            steps.append(f"google {r}")
            if r == "none":
                state = "NO_GOOGLE_BUTTON"
                break
            poll_url(a.port, tid, min(30, budget_left()))
            continue
        if not google_seen and not clicked["vercel"] and any(
                s in low for s in ("sign in with vercel", "log in with", "sign in to continue")):
            r = _click(a.port, tid, "vercel")
            clicked["vercel"] = True
            steps.append(f"site-sso {r}")
            poll_url(a.port, tid, min(30, budget_left()))
            continue
        # two-step gate (chatgpt.com style): no google button yet, but a plain
        # Log in / Sign up control opens the in-page modal that offers Google.
        if (has_google and clicked["google"] is False) or (
                not has_google and not clicked["gate"] and not google_seen):
            r = _click(a.port, tid, "gate") if not has_google else None
            if r:  # clicked a Log in/Sign up control; re-scan next round
                clicked["gate"] = True
                steps.append(f"gate {r}")
                time.sleep(2)
                continue
        # maybe SSO completed and we are back but session not yet applied
        probe = probe_state(a.port, tid, wake_url=a.url)
        if not probe.get("signedOut"):
            state = None
            break
        if clicked["google"] and host != src_host and src_host not in host:
            # OAuth client surface lost (e.g. vercel error page): return home
            tab = Tab(a.port, tid)
            try:
                tab.call("Page.navigate", {"url": a.url})
            finally:
                tab.close()
            poll_url(a.port, tid, min(20, budget_left()))
            continue
        state = "LOGIN_REQUIRED"
        steps.append(f"no usable auth control on {host}")
        break

    if state is None:
        # back on the site: ensure we are ON the original surface, then classify
        tid = resolve_tid(a.port, src_host, tid, None)
        listing = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{a.port}/json/list", timeout=20).read())
        t = next((x for x in listing if x.get("id") == tid), None)
        url = (t or {}).get("url") or ""
        if src_host not in _host(url):
            tab = Tab(a.port, tid)
            try:
                tab.call("Page.navigate", {"url": a.url})
            finally:
                tab.close()
            poll_url(a.port, tid, min(20, budget_left()))
        probe = probe_state(a.port, tid, wake_url=a.url)
        ev, body, furl = _evidence(a.port, tid, _host(probe.get("url", "")) or src_host)
        if body_is_hard_wall(body.lower()):
            return out({"state": "WALL", "finalUrl": furl, "steps": steps,
                        "authCookieNames": ev})
        cls = classify_final_provider_state(furl, body.lower(), bool(ev))
        if probe.get("signedOut") and cls in ("SSO_PROVIDER_SESSION_OBSERVED",):
            cls = "LOGIN_REQUIRED"
        return out({"state": cls, "finalUrl": furl, "steps": steps,
                    "authCookieNames": ev})
    return out({"state": state, "steps": steps})


def _host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def resolve_tid(port, host, tid, url):
    """Wake-navigating a frozen tab can CHANGE its target id. Never trust a
    stale tid: resolve the live target by host match, else tid match."""
    listing = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=20).read())
    pages = [t for t in listing
             if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    for t in pages:
        if _host(t.get("url") or "") == host:
            return t["id"]
    for t in pages:
        if t["id"] == tid:
            return tid
    raise RuntimeError(f"no live target for {host}")


def wake(port, tid, url, wait=5.0):
    """Chrome freezes background tabs (Memory Saver); a frozen renderer never
    answers Runtime.evaluate. /json/activate + one browser-dispatched navigate
    to the tab's OWN url re-creates the execution context (seat_signup_matrix
    8.2 recovery pattern). Reload of the same URL: no typing, no navigation
    decision, no state change beyond the page re-rendering."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/activate/{tid}", timeout=10)
    except Exception:
        pass
    time.sleep(2)
    try:
        tab = Tab(port, tid, timeout=15)
        tab.call_deadline = 15
        try:
            tab.call("Page.navigate", {"url": url})
        finally:
            tab.close()
    except Exception:
        pass
    time.sleep(wait)


def probe_state(port, tid, wake_url=None):
    """Live signed-out probe. If the tab is frozen, wake it once and retry."""
    probe_js = (
        "(() => { const t = document.body ? document.body.innerText.slice(0,3000)"
        ".toLowerCase() : '';"
        "const out = /(^|\\n)\\s*(log in|sign in|sign up|get started|create account|"
        "continue with google|登录|登陆)/.test(t)"
        " || /\\/login|\\/signin|\\/sign-in|\\/sign\\b|\\/auth|get-started|authenticate/"
        ".test(location.href);"
        "return JSON.stringify({url: location.href, signedOut: out}); })()")
    try:
        tab = Tab(port, tid)
        try:
            return json.loads(tab.evaluate(probe_js) or "{}")
        finally:
            tab.close()
    except Exception:
        if not wake_url:
            raise
    wake(port, tid, wake_url)
    tab = Tab(port, tid)
    try:
        return json.loads(tab.evaluate(probe_js) or "{}")
    finally:
        tab.close()


def _click(port, tid, js):
    tab = Tab(port, tid)
    try:
        return tab.evaluate(CLICK_JS[js])
    except Exception as e:
        return f"error:{type(e).__name__}"
    finally:
        tab.close()


def _evidence(port, tid, host):
    auth, names, body, url = [], [], "", ""
    tab = Tab(port, tid, timeout=15)
    tab.call_deadline = 12
    try:
        try:
            res = tab.call("Network.getCookies", {"urls": [f"https://{host}"]})
            names = sorted({c.get("name", "") for c in res.get("cookies", [])})
        except Exception:
            pass
        try:
            url = tab.evaluate("location.href")
            body = tab.evaluate(BODY_JS % 2500)
        except Exception:
            pass
        try:
            data = tab.call("Page.captureScreenshot", {"format": "png"}).get("data")
            if data:
                EVID.mkdir(parents=True, exist_ok=True)
                (EVID / f"fleet_{host.replace('.', '_')}_{int(time.time())}.png").write_bytes(
                    base64.b64decode(data))
        except Exception:
            pass  # screenshot is best-effort; cookie/body evidence already taken
    finally:
        tab.close()
    auth = [n for n in names if any(k in n.lower()
            for k in ("token", "session", "auth", "jwt", "sid"))]
    return auth, body, url


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("targets"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--contains", default="")
    p = sub.add_parser("probe"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True)
    p = sub.add_parser("read"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True); p.add_argument("--max", type=int, default=700)
    p = sub.add_parser("click"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True); p.add_argument("--js", required=True,
        choices=list(CLICK_JS))
    p = sub.add_parser("nav"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True); p.add_argument("--url", required=True)
    p = sub.add_parser("shot"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True); p.add_argument("--name", required=True)
    p = sub.add_parser("find")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True)
    p = sub.add_parser("cookies"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True); p.add_argument("--url", required=True)
    p = sub.add_parser("sso"); p.add_argument("--port", type=int, required=True)
    p.add_argument("--tid", required=True); p.add_argument("--url", required=True)
    p.add_argument("--budget", type=int, default=300)
    a = ap.parse_args()
    fn = {"targets": cmd_targets, "probe": cmd_probe, "read": cmd_read,
          "click": cmd_click, "nav": cmd_nav, "shot": cmd_shot, "find": cmd_find,
          "cookies": cmd_cookies, "sso": cmd_sso}[a.cmd]
    sys.exit(fn(a))


if __name__ == "__main__":
    main()
