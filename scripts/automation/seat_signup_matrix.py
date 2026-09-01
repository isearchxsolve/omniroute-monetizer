#!/usr/bin/env python3
"""Gate 1: per-profile onboarding matrix runner (ordinary Google-SSO only).

Usage:
  python seat_signup_matrix.py --port 9223 --seat niloy --provider blackbox --url https://www.blackbox.ai/

One bounded attempt per invocation -> one terminal artifact
state/signup_resolution_<seat>_<provider>.json with terminal_state in
SSO_PROVIDER_SESSION_OBSERVED / SIGNUP_COMPLETED / EXISTING_ACCOUNT /
LOGIN_REQUIRED / WALL / SSO_INITIATED / ONBOARDING_VERIFICATION_REQUIRED.

Safety: attach-only via chrome_live_guard.assert_cdp_safe; never navigates an
existing tab whose URL does not already belong to the candidate host (video-seat
project tabs on 9224/9225 are untouchable); creates a fresh tab for unmatched
candidates and closes it at the end. No password/OTP/CAPTCHA/MFA handling.
"""
import argparse
import base64
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_cdp_safe  # noqa: E402
from signup_classify import (  # noqa: E402
    classify_final_provider_state, classify_pre_sso_surface)
import websocket  # noqa: E402

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
EVID = ROOT / "state" / "signup_evidence"
EVID.mkdir(parents=True, exist_ok=True)
GOOGLE_AUTH_NAMES = {"SAPISID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID"}


class Stop(Exception):
    pass


def targets(port):
    return json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=15).read())


class Tab:
    def __init__(self, port, target_id, timeout=25):
        mine = next((t for t in targets(port)
                     if t.get("id") == target_id and t.get("webSocketDebuggerUrl")), None)
        if mine is None:
            raise Stop(f"target {target_id[:12]} gone")
        self.tid = target_id
        self.port = port
        self.ws = websocket.create_connection(mine["webSocketDebuggerUrl"],
                                              timeout=timeout, max_size=64 * 1024 * 1024)
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        want = self._id
        self.ws.send(json.dumps({"id": want, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.monotonic()))
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if msg.get("id") == want:
                if "error" in msg:
                    raise Stop(f"{method}: {msg['error']}")
                return msg.get("result") or {}
        raise Stop(f"{method} timeout")

    def evaluate(self, expression):
        res = self.call("Runtime.evaluate", {"expression": expression,
                                             "returnByValue": True, "awaitPromise": False})
        return str((res.get("result") or {}).get("value") or "")

    def url(self):
        try:
            return self.call("Runtime.evaluate", {
                "expression": "location.href",
                "returnByValue": True}).get("result", {}).get("value", "")
        except Exception:
            return ""

    def screenshot(self, name):
        try:
            data = self.call("Page.captureScreenshot", {"format": "png"}).get("data")
            if data:
                (EVID / name).write_bytes(base64.b64decode(data))
                return name
        except Exception:
            pass
        return None

    def close_ws(self):
        try:
            self.ws.close()
        except Exception:
            pass


def new_tab(port, url):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe='')}",
            method="PUT"), timeout=15).read())["id"]


def close_tab(port, tid):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{tid}", timeout=10)
    except Exception:
        pass


def wake_tab(port, tid, url):
    """8.2 recovery: /json/activate re-creates the execution context; if evaluation
    still hangs, one browser-dispatched Page.navigate to the same URL."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/activate/{tid}", timeout=10)
    except Exception:
        pass
    time.sleep(2)
    try:
        t = Tab(port, tid, timeout=20)
        try:
            t.call("Page.navigate", {"url": url})
        finally:
            t.close_ws()
    except Exception:
        pass
    time.sleep(3)


def evaluate_with_wake(tab, port, tid, expression, url, attempts=2):
    for i in range(attempts):
        try:
            return tab.evaluate(expression)
        except Stop as e:
            if "timeout" not in str(e) or i == attempts - 1:
                raise
            steps_safe = f"wake_retry_{i + 1}"
            print("[wake]", steps_safe)
            wake_tab(port, tid, url)
            time.sleep(3)
    raise Stop("evaluate exhausted wake retries")


def settle(tab, want_host, wait=12):
    deadline = time.monotonic() + wait
    last, stable = "", 0
    while time.monotonic() < deadline:
        time.sleep(1.5)
        now = tab.url()
        if now and now == last:
            stable += 1
            if stable >= 2:
                return now
        else:
            stable, last = 0, now
    return last


def cookie_names(tab, url):
    try:
        res = tab.call("Network.getCookies", {"urls": [url]})
        return sorted({c.get("name", "") for c in res.get("cookies", [])})
    except Exception:
        return []


PROBE_JS = (
    "(() => { const t = document.body ? document.body.innerText.slice(0, 3000)"
    ".toLowerCase() : '';"
    "const out = /(^|\\n)\\s*(log in|sign in|sign up|get started|create account|"
    "continue with google|sign up with google)/.test(t)"
    " || /\\/login|\\/signin|\\/sign-in|\\/sign\\b|\\/auth|get-started/"
    ".test(location.href);"
    "return JSON.stringify({url: location.href, signedOut: out}); })()"
)
GOOGLE_CLICK_JS = (
    "(() => { const cands = Array.from(document.querySelectorAll("
    "'button, a, [role=\"button\"], div[role=\"link\"]'));"
    "const hit = cands.find(el => {"
    " if (el.offsetParent === null && el.getClientRects().length === 0) return false;"
    " const s = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')"
    " + ' ' + (el.getAttribute('data-provider') || '') + ' '"
    " + (el.getAttribute('href') || '')).toLowerCase();"
    " return s.includes('google') || s.includes('accounts.google.com'); });"
    "if (!hit) return 'none';"
    "hit.click();"
    "return 'clicked:' + (hit.innerText || hit.getAttribute('aria-label') || '')"
    ".slice(0, 40); })()"
)
CHOOSER_CLICK_JS = (
    "(() => { const acc = document.querySelector('[data-identifier]')"
    " || document.querySelector('div[role=\"link\"][tabindex]');"
    "if (!acc) return 'none';"
    "acc.click();"
    "return 'clicked:' + (acc.getAttribute('data-identifier') || 'account'); })()"
)
CONSENT_CLICK_JS = (
    "(() => { const b = Array.from(document.querySelectorAll('button, div[role=\"button\"]'))"
    ".find(el => /continue|allow|i agree/i.test(el.innerText || ''));"
    "if (b) { b.click(); return 'consent'; } return 'none'; })()"
)
WALL_SIGN = re.compile(
    r"verify your email|verification code|enter the code|captcha|unusual traffic|"
    r"check your email|confirm your email|otp", re.I)


def record(seat, provider, state, identity, evidence, steps, wall=None):
    doc = {
        "terminal_state": state,
        "provider": provider,
        "account_identity": identity,
        "seat": seat,
        "evidence": evidence,
        "steps": steps,
        "wall": wall,
        "premise_compliance": {
            "password_typed": False, "otp_handled": False, "captcha_solved": False,
            "mfa_bypassed": False, "operator_profile_touched": False,
            "chrome_launched": False, "service_touched": False,
        },
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = ROOT / "state" / f"signup_resolution_{seat}_{provider}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(out)
    print("ARTIFACT:", out.name, "->", state)
    return doc


def classify_provider_surface(body_low, url_low):
    if WALL_SIGN.search(body_low or ""):
        return "WALL"
    if re.search(r"sign (in|up)|log ?in|create account|get started", body_low or ""):
        return "SIGNED_OUT"
    return "SIGNED_IN"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--seat", required=True)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--budget", type=int, default=150)
    args = ap.parse_args()

    cdp = f"http://127.0.0.1:{args.port}"
    assert_cdp_safe(cdp, who=f"seat_signup_matrix_{args.seat}")
    host = urllib.parse.urlsplit(args.url).hostname or ""
    steps, evidence = [], []
    t0 = time.monotonic()
    created = None

    existing = next((t for t in targets(args.port)
                     if t.get("type") == "page" and host in (t.get("url") or "")), None)
    if existing:
        tid = existing["id"]
        steps.append(f"reused_existing_tab {tid[:12]}")
    else:
        tid = new_tab(args.port, args.url)
        created = tid
        steps.append(f"created_tab {tid[:12]}")

    tab = None
    try:
        tab = Tab(args.port, tid)
        final = settle(tab, host)
        steps.append(f"landed {final[:90]}")
        ev = tab.screenshot(f"{args.provider}_{args.seat}_landing.png")
        if ev:
            evidence.append(ev)

        g_names = cookie_names(tab, "https://accounts.google.com")
        g_ok = bool(GOOGLE_AUTH_NAMES & set(g_names))
        steps.append(f"google_session={'present' if g_ok else 'absent'} (names={len(g_names)})")
        if not g_ok:
            record(args.seat, args.provider, "LOGIN_REQUIRED", "not_disclosed", evidence,
                   steps, wall=f"{args.seat} profile has no authenticated Google SSO "
                               "session; operator one-time human sign-in required")
            return 0

        try:
            probe_raw = evaluate_with_wake(tab, args.port, tid, PROBE_JS, final or args.url)
        except Stop as e:
            record(args.seat, args.provider, "WALL", "not_disclosed", evidence, steps,
                   wall=f"tab renderer unresponsive after wake attempts ({e}); "
                        "manual revisit needed")
            return 0
        try:
            probe = json.loads(probe_raw)
        except ValueError:
            probe = {"url": final, "signedOut": True}
        steps.append(f"probe signedOut={probe.get('signedOut')}")
        if not probe.get("signedOut"):
            # Already-authenticated surface before any SSO click. An EXISTING
            # account (never a new signup); an onboarding/questionnaire page is
            # ONBOARDING_VERIFICATION_REQUIRED.
            try:
                pre_body = tab.evaluate(
                    "document.body ? document.body.innerText.slice(0,2500) : ''").lower()
                pre_cookies = cookie_names(tab, f"https://{host}")
                pre_auth = [n for n in pre_cookies
                            if any(k in n.lower() for k in
                                   ("token", "session", "auth", "jwt", "sid"))]
            except Exception:
                pre_body, pre_auth = "", []
            pre = classify_pre_sso_surface(final, pre_body, bool(pre_auth))
            steps.append(f"pre-sso classify={pre} (provider_auth_cookies={len(pre_auth)})")
            if pre in ("EXISTING_ACCOUNT", "ONBOARDING_VERIFICATION_REQUIRED",
                       "SIGNUP_COMPLETED"):
                record(args.seat, args.provider, pre, "existing_seat_session",
                       evidence, steps)
            else:
                record(args.seat, args.provider, "EXISTING_ACCOUNT",
                       "existing_seat_session", evidence, steps)
            return 0

        clicked = tab.evaluate(GOOGLE_CLICK_JS)
        steps.append(f"google-button {clicked[:60]}")
        if clicked == "none":
            record(args.seat, args.provider, "LOGIN_REQUIRED", "not_disclosed", evidence,
                   steps, wall="auth surface exposes no Google-SSO button "
                               "(email/password-only or closed signup)")
            return 0

        gtab = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and gtab is None:
            time.sleep(1.5)
            for t in targets(args.port):
                if t.get("type") == "page" and "accounts.google.com" in (t.get("url") or ""):
                    gtab = t
                    break
        if gtab is None:
            record(args.seat, args.provider, "LOGIN_REQUIRED", "not_disclosed", evidence,
                   steps, wall="no Google OAuth surface appeared after SSO click")
            return 0

        gt = Tab(args.port, gtab["id"])
        identity = "not_disclosed"
        try:
            gurl = gtab.get("url") or gt.url()
            steps.append(f"google surface {gurl[:90]}")
            ev = gt.screenshot(f"{args.provider}_{args.seat}_google.png")
            if ev:
                evidence.append(ev)
            low = gurl.lower()
            if "accountchooser" not in low and any(
                    s in low for s in ("/v3/signin/identifier", "/v3/signin/v2/pwd",
                                       "captcha", "challenge", "recovery")):
                record(args.seat, args.provider, "LOGIN_REQUIRED", identity, evidence,
                       steps, wall=f"Google demands interactive re-auth: {gurl[:120]}")
                return 0
            chooser = "none"
            for _ in range(3):
                chooser = gt.evaluate(CHOOSER_CLICK_JS)
                if chooser != "none":
                    break
                time.sleep(2.5)
            steps.append(f"chooser {chooser[:60]}")
            if chooser != "none":
                identity = chooser.split("clicked:", 1)[-1]
            else:
                gurl2 = gt.url()
                if any(s in gurl2.lower() for s in
                       ("/v3/signin/identifier", "/v3/signin/v2/pwd")):
                    record(args.seat, args.provider, "LOGIN_REQUIRED", identity, evidence,
                           steps, wall="Google chooser absent; interactive sign-in required")
                    return 0
            consent_clicked = 0
            deadline = time.monotonic() + min(60, args.budget - (time.monotonic() - t0))
            back = None
            while time.monotonic() < deadline:
                time.sleep(2)
                cur = targets(args.port)
                if consent_clicked < 1:
                    for t in cur:
                        u = (t.get("url") or "").lower()
                        if "accounts.google.com" in u and any(
                                s in u for s in ("consent", "approval", "oauthchooseaccount")):
                            try:
                                ct = Tab(args.port, t["id"])
                                try:
                                    if ct.evaluate(CONSENT_CLICK_JS) == "consent":
                                        consent_clicked += 1
                                        steps.append("consent continue clicked")
                                finally:
                                    ct.close_ws()
                            except Exception:
                                pass
                            break
                urls = [t.get("url") or "" for t in cur if t.get("type") == "page"]
                back = next((u for u in urls if host in u), None)
                if back and "accounts.google.com" not in back:
                    break
            if not back:
                # Google SSO was genuinely initiated (chooser+consent) but the
                # provider never redirected back to a usable surface. SSO_INITIATED,
                # not a completed signup.
                record(args.seat, args.provider, "SSO_INITIATED", identity, evidence,
                        steps, wall="Google SSO initiated (chooser+consent) but no "
                                     "redirect back to provider surface within budget; "
                                     "provider onboarding did not complete to a usable account")
                return 0
            steps.append(f"redirect {back[:90]}")
            time.sleep(3)

            auth_like, body_low, final_url = [], "", back
            for t in targets(args.port):
                if host in (t.get("url") or ""):
                    t2 = Tab(args.port, t["id"])
                    try:
                        ev = t2.screenshot(f"{args.provider}_{args.seat}_after_sso.png")
                        if ev:
                            evidence.append(ev)
                        h_cookies = cookie_names(t2, f"https://{host}")
                        auth_like = [n for n in h_cookies
                                     if any(k in n.lower() for k in
                                            ("token", "session", "auth", "jwt", "sid"))]
                        body_low = t2.evaluate(
                            "document.body ? document.body.innerText.slice(0,2500)"
                            ".toLowerCase() : ''")
                        final_url = t2.url() or back
                        steps.append(f"provider cookies={len(h_cookies)}"
                                     f" auth_like={auth_like[:6]}")
                    except Exception as e:
                        steps.append(f"classification probe degraded: {type(e).__name__}")
                    finally:
                        t2.close_ws()
                    break

            if WALL_SIGN.search(body_low or ""):
                record(args.seat, args.provider, "WALL", identity, evidence, steps,
                        wall="provider demands email verification / OTP / captcha after "
                             "SSO redirect (premise: not handled)")
                return 0
            # Honest acceptance gate (MASTER_WORKLOG.md #1404 / D:/conversations.txt):
            # SIGNUP_COMPLETED requires the provider's FINAL authenticated
            # account/dashboard surface AND an independently verified protected
            # provider session. An onboarding/survey/questionnaire surface is
            # ONBOARDING_VERIFICATION_REQUIRED, never success.
            final_state = classify_final_provider_state(final_url, body_low, bool(auth_like))
            if final_state == "ONBOARDING_VERIFICATION_REQUIRED":
                record(args.seat, args.provider, "ONBOARDING_VERIFICATION_REQUIRED",
                        identity if identity != "not_disclosed"
                        else f"{args.seat}_google_sso_account", evidence, steps,
                        wall="SSO redirect reached a provider onboarding/questionnaire "
                             "surface; account not yet verified for use. Human completion "
                             "required if email/OTP/CAPTCHA/MFA is demanded -- never bypassed.")
                return 0
            if final_state == "SIGNUP_COMPLETED":
                record(args.seat, args.provider, "SIGNUP_COMPLETED",
                        identity if identity != "not_disclosed"
                        else f"{args.seat}_google_sso_account", evidence, steps)
                return 0
            if final_state == "SSO_PROVIDER_SESSION_OBSERVED":
                # Auth-like session cookies were observed on the post-SSO
                # provider surface, but no provider-specific account-creation
                # evidence and no successful harmless provider action were proven.
                # This is a provisional observation, NOT a counted signup.
                record(args.seat, args.provider, "SSO_PROVIDER_SESSION_OBSERVED",
                        identity if identity != "not_disclosed"
                        else f"{args.seat}_google_sso_account", evidence, steps,
                        wall="SSO redirect reached a provider surface with auth-like "
                             "session cookies, but no provider-specific account-creation "
                             "evidence and no successful harmless provider action were "
                             "observed. Provisional SSO/provider-session observation only "
                             "-- NOT a new signup (no capacity claim).")
                return 0
            record(args.seat, args.provider, "LOGIN_REQUIRED", identity, evidence,
                    steps, wall="SSO redirect completed but no authenticated provider "
                                "dashboard surface / protected session observed")
            return 0
        finally:
            gt.close_ws()
    finally:
        if tab is not None:
            tab.close_ws()
        if created:
            close_tab(args.port, created)


if __name__ == "__main__":
    sys.exit(main())
