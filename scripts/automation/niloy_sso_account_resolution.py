#!/usr/bin/env python3
"""Atomic niloy account-resolution unit: ONE candidate (app.hyperbolic.ai), ONE terminal record.

Scope contract (worklog #1394): emits exactly one of SIGNUP_COMPLETED / EXISTING_ACCOUNT /
LOGIN_REQUIRED / WALL into state/signup_resolution_niloy_hyperbolic.json. Attaches read-only
to the EXISTING dedicated seat Chrome on :9223 (never launches Chrome, never touches the
operator's live profile, never touches services). Ordinary Google-SSO signup UI only: no
password typing, no OTP/email-code handling, no CAPTCHA, no MFA bypass, no credential invention.
"""
import base64
import json
import pathlib
import re
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_cdp_safe  # noqa: E402
from signup_classify import (  # noqa: E402
    classify_final_provider_state, classify_pre_sso_surface)
import websocket  # noqa: E402

PORT = 9223
CDP = f"http://127.0.0.1:{PORT}"
TARGET_URL = "https://app.hyperbolic.ai/"
PROVIDER = "hyperbolic"
SEAT = "niloy"
ROOT = pathlib.Path(r"D:\omniroute-monetizer")
EVID = ROOT / "state" / "signup_evidence"
ARTIFACT = ROOT / "state" / "signup_resolution_niloy_hyperbolic.json"
BUDGET_S = 150
GOOGLE_AUTH_NAMES = {"SAPISID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID"}

EVID.mkdir(parents=True, exist_ok=True)


class Stop(Exception):
    pass


def targets():
    return json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=15).read())


class Tab:
    def __init__(self, target_id, timeout=25):
        mine = next((t for t in targets()
                     if t.get("id") == target_id and t.get("webSocketDebuggerUrl")), None)
        if mine is None:
            raise Stop(f"target {target_id[:12]} gone")
        self.tid = target_id
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
        return self.call("Runtime.evaluate", {
            "expression": "location.href", "returnByValue": True}).get("result", {}).get("value", "")

    def screenshot(self, name):
        try:
            data = self.call("Page.captureScreenshot", {"format": "png"}).get("data")
            if data:
                (EVID / name).write_bytes(base64.b64decode(data))
                return name
        except Exception:
            pass
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def pick_tab():
    ts = [t for t in targets() if t.get("type") == "page"]
    for t in ts:
        if "hyperbolic" in (t.get("url") or ""):
            return t["id"]
    for t in ts:
        if not (t.get("url") or "").startswith("chrome"):
            return t["id"]
    req = urllib.request.Request(f"{CDP}/json/new?{TARGET_URL}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["id"]


def settle(tab, want_host, wait=12):
    deadline = time.monotonic() + wait
    last, stable = "", 0
    while time.monotonic() < deadline:
        time.sleep(1.5)
        try:
            now = tab.url()
        except Exception:
            now = ""
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


def record(state, identity, evidence, steps, wall=None):
    doc = {
        "terminal_state": state,
        "provider": PROVIDER,
        "account_identity": identity,
        "seat": SEAT,
        "cdp_port": PORT,
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
    tmp = ARTIFACT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(ARTIFACT)
    print(json.dumps({"terminal_state": state, "provider": PROVIDER,
                      "account_identity": identity, "artifact": str(ARTIFACT),
                      "evidence": evidence}, indent=2))


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
PROBE_JS = (
    "(() => { const t = document.body ? document.body.innerText.slice(0, 3000)"
    ".toLowerCase() : '';"
    "const out = /(^|\\n)\\s*(log in|sign in|sign up|get started|create account|"
    "continue with google)/.test(t)"
    " || /\\/login|\\/signin|\\/sign-in|\\/auth|get-started/.test(location.href);"
    "return JSON.stringify({url: location.href, signedOut: out}); })()"
)


def main():
    assert_cdp_safe(CDP, who="niloy_sso_account_resolution")
    steps, evidence = [], []
    t0 = time.monotonic()

    tid = pick_tab()
    steps.append(f"tab {tid[:12]}")
    tab = Tab(tid)
    try:
        g_names = cookie_names(tab, "https://accounts.google.com")
        g_ok = bool(GOOGLE_AUTH_NAMES & set(g_names))
        steps.append(f"google_session={'present' if g_ok else 'absent'}"
                     f" (names={len(g_names)})")
        if not g_ok:
            record("LOGIN_REQUIRED", "not_disclosed", {"evidence_dir": str(EVID)}, steps,
                   wall="niloy profile has no authenticated Google SSO session; "
                        "operator must complete the one human Google sign-in")
            return 0

        tab.call("Page.navigate", {"url": TARGET_URL})
        final = settle(tab, "hyperbolic")
        steps.append(f"landed {final[:90]}")
        ev = tab.screenshot("hyperbolic_landing_niloy.png")
        if ev:
            evidence.append(ev)

        probe_raw = tab.evaluate(PROBE_JS)
        try:
            probe = json.loads(probe_raw)
        except ValueError:
            probe = {"url": final, "signedOut": True}
        steps.append(f"probe signedOut={probe.get('signedOut')}")
        if not probe.get("signedOut"):
            # Surface was already authenticated before any SSO click. This is an
            # EXISTING account, never a new signup -- and if it is in fact an
            # onboarding/questionnaire page, it is ONBOARDING_VERIFICATION_REQUIRED.
            identity = "not_disclosed"
            body_low = ""
            p_auth = []
            try:
                body = tab.evaluate(
                    "document.body ? document.body.innerText.slice(0,3000) : ''")
                body_low = (body or "").lower()
                m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", body or "")
                if m:
                    identity = m.group(0)
                p_cookies = cookie_names(tab, "https://app.hyperbolic.ai")
                p_auth = [n for n in p_cookies
                          if any(k in n.lower() for k in
                                 ("token", "session", "auth", "jwt", "sid"))]
            except Exception:
                pass
            pre = classify_pre_sso_surface(final, body_low, bool(p_auth))
            steps.append(f"pre-sso classify={pre} (provider_auth_cookies={len(p_auth)})")
            if pre in ("EXISTING_ACCOUNT", "ONBOARDING_VERIFICATION_REQUIRED",
                       "SIGNUP_COMPLETED"):
                record(pre, identity or "existing_niloy_session", evidence, steps)
            else:
                record("EXISTING_ACCOUNT", identity or "existing_niloy_session",
                        evidence, steps)
            return 0

        clicked = tab.evaluate(GOOGLE_CLICK_JS)
        steps.append(f"google-button {clicked[:60]}")
        if clicked == "none":
            record("LOGIN_REQUIRED", "not_disclosed", evidence, steps,
                   wall="auth surface exposes no Google-SSO button (email/password only)")
            return 0

        gtab = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and gtab is None:
            time.sleep(1.5)
            for t in targets():
                if t.get("type") == "page" and "accounts.google.com" in (t.get("url") or ""):
                    gtab = t
                    break
        if gtab is None:
            record("LOGIN_REQUIRED", "not_disclosed", evidence, steps,
                   wall="no Google OAuth surface appeared after SSO click")
            return 0

        gt = Tab(gtab["id"])
        try:
            gurl = gtab.get("url") or gt.url()
            steps.append(f"google surface {gurl[:90]}")
            ev = gt.screenshot("hyperbolic_google_surface_niloy.png")
            if ev:
                evidence.append(ev)
            low = gurl.lower()
            is_chooser = "accountchooser" in low
            interactive = (not is_chooser) and any(
                s in low for s in ("/v3/signin/identifier", "/v3/signin/v2/pwd",
                                   "captcha", "challenge", "recovery"))
            if interactive:
                record("LOGIN_REQUIRED", "not_disclosed", evidence, steps,
                       wall=f"Google demands interactive re-auth: {gurl[:120]}")
                return 0
            chooser = "none"
            for _ in range(3):
                chooser = gt.evaluate(CHOOSER_CLICK_JS)
                if chooser != "none":
                    break
                time.sleep(2.5)
            steps.append(f"chooser {chooser[:60]}")
            if chooser == "none":
                gurl2 = gt.url()
                if any(s in gurl2.lower() for s in
                       ("/v3/signin/identifier", "/v3/signin/v2/pwd")):
                    record("LOGIN_REQUIRED", "not_disclosed", evidence, steps,
                           wall="Google chooser absent; interactive sign-in required")
                    return 0
            else:
                identity = chooser.split("clicked:", 1)[-1]
            consent_clicked = 0
            deadline = time.monotonic() + min(60, BUDGET_S - (time.monotonic() - t0))
            back = None
            while time.monotonic() < deadline:
                time.sleep(2)
                cur = targets()
                if consent_clicked < 1:
                    for t in cur:
                        u = (t.get("url") or "").lower()
                        if "accounts.google.com" in u and ("consent" in u or
                                                           "approval" in u or
                                                           "oauthchooseaccount" in u):
                            try:
                                ct = Tab(t["id"])
                                try:
                                    r = ct.evaluate(
                                        "(() => { const b = Array.from(document."
                                        "querySelectorAll('button, div[role=\"button\"]'))"
                                        ".find(el => /continue|allow|i agree/i.test"
                                        "(el.innerText || ''));"
                                        "if (b) { b.click(); return 'consent'; }"
                                        "return 'none'; })()")
                                    if r == "consent":
                                        consent_clicked += 1
                                        steps.append("consent continue clicked")
                                finally:
                                    ct.close()
                            except Exception:
                                pass
                            break
                urls = [t.get("url") or "" for t in cur if t.get("type") == "page"]
                back = next((u for u in urls if "hyperbolic" in u), None)
                if back and "accounts.google.com" not in back:
                    break
            if not back:
                # Google SSO was genuinely initiated (chooser selected + consent
                # continued) but the provider never redirected back to a usable
                # surface. That is SSO_INITIATED, NOT a completed signup.
                record("SSO_INITIATED", identity if chooser != "none" else "not_disclosed",
                        evidence, steps,
                        wall="Google SSO initiated (chooser+consent) but no redirect "
                             "back to provider surface within budget; provider "
                             "onboarding did not complete to a usable account")
                return 0
            steps.append(f"redirect {back[:90]}")

            auth_like, signed_in_surface = [], False
            try:
                for t in targets():
                    if "hyperbolic" in (t.get("url") or ""):
                        tab2 = Tab(t["id"])
                        try:
                            ev = tab2.screenshot("hyperbolic_after_sso_niloy.png")
                            if ev and ev not in evidence:
                                evidence.append(ev)
                            h_cookies = cookie_names(tab2, "https://app.hyperbolic.ai")
                            auth_like = [n for n in h_cookies
                                         if any(k in n.lower() for k in
                                                ("token", "session", "auth", "jwt", "sid"))]
                            body_low = tab2.evaluate(
                                "document.body ? document.body.innerText.slice(0,2000)"
                                ".toLowerCase() : ''")
                            signed_in_surface = not probe_fn(body_low)
                            steps.append(f"provider cookies={len(h_cookies)}"
                                         f" auth_like={auth_like[:6]}")
                        finally:
                            tab2.close()
                        break
            except Exception as e:
                steps.append(f"classification probe degraded: {type(e).__name__}")
            # Honest acceptance gate (MASTER_WORKLOG.md #1404 / D:/conversations.txt):
            # SIGNUP_COMPLETED requires the provider's FINAL authenticated
            # account/dashboard surface AND an independently verified protected
            # provider session. An onboarding/survey/questionnaire surface is
            # ONBOARDING_VERIFICATION_REQUIRED, never success.
            final_state = classify_final_provider_state(back, body_low, bool(auth_like))
            if final_state == "ONBOARDING_VERIFICATION_REQUIRED":
                record("ONBOARDING_VERIFICATION_REQUIRED",
                        identity if chooser != "none" else "not_disclosed",
                        evidence, steps,
                        wall="SSO redirect reached a provider onboarding/questionnaire "
                             "surface; the account is not yet verified for use. Automation "
                             "stops; a human must complete it only if email/OTP/CAPTCHA/MFA "
                             "is demanded -- never bypassed.")
                return 0
            if final_state == "SIGNUP_COMPLETED":
                record("SIGNUP_COMPLETED",
                        identity if chooser != "none" else "existing_google_account",
                        evidence, steps)
                return 0
            record("LOGIN_REQUIRED", identity if chooser != "none" else "not_disclosed",
                    evidence, steps,
                    wall="SSO redirect completed but no authenticated provider "
                         "dashboard surface / protected session observed")
            return 0
        finally:
            gt.close()
    finally:
        tab.close()


def probe_fn(body_low):
    import re
    return bool(re.search(r"sign in|log in|sign up|create account|get started", body_low or ""))


if __name__ == "__main__":
    sys.exit(main())
