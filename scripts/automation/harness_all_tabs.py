#!/usr/bin/env python3
"""harness_all_tabs.py -- convert non-eligible tabs into capturable seats.

The graduation funnel (tab_graduation_sweep.py -> graduate_all_seats.py) only
captures a tab that is (a) on a known site, (b) authenticated, (c) already
sitting on its chat surface, and (d) not in the video lane.  On 2026-08-29,
53 of 74 open tabs failed one of those gates.  This harness is the explicit,
sanctioned pass that fixes what can be fixed WITHOUT capturing anything:

  REQUIRES_NAVIGATION   verify the tab already sits on its chat surface (most
                        do); navigate only the ones that do not
  SKIP_NOT_AUTHENTICATED  open the site; if signed out, click the Google SSO
                        button once (the automation profile's Google session is
                        live), then at most one chooser click and one consent
                        click.  A password wall, a consent wall that survives
                        one bounded click, or any hard wall (captcha / OTP /
                        card / quota) is a reportable outcome -- never typed,
                        never bypassed.
  UNSUITABLE_PAGE       navigate away from cookie-mismatch / get-started pages
  UNMANAGED_TAB         report only (registry additions are a separate edit)
  VIDEO_SEPARATE_GRADUATION / TRANSPORT_WEBSOCKET  listed, never touched

Modality note (operator, 2026-08-29): most chat providers ALSO carry video
models.  Graduating the chat surface does not exhaust a seat's value; video
graduation stays a separate spend-gated lane and is only recorded here.

Hardening contract (2026-08-31):
  * every SSO terminal label comes from signup_classify.VALID_TERMINAL_STATES;
    there is no parallel taxonomy, and any non-canonical label raises
  * each SSO row carries provider evidence: final URL (query strings
    redacted), cookie NAMES (never values), body snippet, one screenshot
  * redirects are validated host-aware: only accounts.google.com or the
    source provider's registrable domain may be followed
  * the whole --apply run is bounded by --budget seconds (default 900);
    rows past the deadline are marked BUDGET_EXCEEDED, never driven
  * this harness stays distinct from the OmniRoute-native chat path; the one
    consumer contract http://127.0.0.1:8190/v1 is untouched

Nothing here captures, replays, or graduates.  After this pass re-run
`graduate_all_seats.py` (plan-only) to see the new funnel, then `--apply`.

    python harness_all_tabs.py                 # plan only -- drives nothing
    python harness_all_tabs.py --apply         # navigate + bounded SSO clicks
    python harness_all_tabs.py --apply --only groq
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import websocket

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tab_graduation_sweep import (  # noqa: E402
    SafetyRefusal,
    assert_automation_seat,
    build_manifest,
    reg,
    safe_url,
    tab_targets,
)
from signup_classify import (  # noqa: E402
    VALID_TERMINAL_STATES,
    body_is_hard_wall,
    classify_final_provider_state,
    classify_pre_sso_surface,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
REPORT = STATE / "tab_harness_report.json"
EVIDENCE = STATE / "tab_harness_evidence"
AUDIT = pathlib.Path(__file__).resolve().parent / "seat_readiness_audit.py"

# Non-terminal SSO labels this harness may emit. Every terminal label must be
# one of signup_classify.VALID_TERMINAL_STATES -- there is no parallel taxonomy.
SSO_NON_TERMINAL_LABELS = {"SSO_NO_GOOGLE_BUTTON", "BUDGET_EXCEEDED"}


def sso_label_is_canonical(label: str) -> bool:
    return label in VALID_TERMINAL_STATES or label in SSO_NON_TERMINAL_LABELS

# Canonical chat surfaces.  The registry (free_llm_chat_sites.json) sometimes
# holds a landing page; these are the URLs a signed-in seat should actually sit
# on for a chat capture.  Sites not listed here fall back to their registry URL.
CHAT_SURFACE = {
    "Groq Chat": "https://console.groq.com/playground",
    "Coze Web": "https://www.coze.com/",
    "Microsoft Copilot Web": "https://copilot.microsoft.com/",
    "SambaNova Cloud Chat": "https://cloud.sambanova.ai/chat",
    "iFlytek SparkDesk": "https://xinghuo.xfyun.cn/desk",
    "Baichuan Web": "https://yi.baichuan-ai.com/",
    "Together AI Chat": "https://api.together.ai/playground",
    "Claude Official Web": "https://claude.ai/new",
    "ChatGPT Free Web": "https://chatgpt.com/",
    "Grok on X / Grok Web": "https://grok.com/",
    "Google Gemini Web": "https://gemini.google.com/app",
    "DuckDuckGo AI Chat (duck.ai)": "https://duck.ai",
    "V0 by Vercel (v0.app)": "https://v0.app/",
    "Giz AI Chat": "https://www.giz.ai/chat",
    "Genspark AI": "https://www.genspark.ai/",
    "Yuewen Chat": "https://yuewen.cn/chat",
    "Creen AI": "https://www.creen.ai/",
}

# Sites whose signed-out state is acceptable to try to repair via the Google
# SSO button.  Everything else classified SKIP_NOT_AUTHENTICATED is reported.
SSO_SITES = {
    "ChatGPT Free Web", "Grok on X / Grok Web", "Coze Web",
    "SambaNova Cloud Chat", "DuckDuckGo AI Chat (duck.ai)", "Giz AI Chat",
    "Genspark AI", "Yuewen Chat", "Creen AI", "V0 by Vercel (v0.app)",
}

# Read-only JS probes / one-click actions.  No typing, no form fills, no
# CAPTCHA interaction -- a wall that survives these is a reportable outcome.
PROBE_JS = (
    "(() => { const t = document.body ? document.body.innerText.slice(0, 3000)"
    ".toLowerCase() : '';"
    "const out = /(^|\\n)\\s*(log in|sign in|sign up|get started|create account|"
    "continue with google|登录|登陆)/.test(t)"
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
    " return (/sign\\s*(in|up)|log\\s*in|continue\\s+with/i.test(s) &&"
    " (s.includes('google') || s.includes('accounts.google.com'))); });"
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
# Bounded consent handling: the single "Continue"/"Allow" control on a Google
# OAuth approval surface. One click, never scripted past a second prompt, and
# identical to the sanctioned pattern in seat_signup_matrix.py (CONSENT_CLICK_JS).
CONSENT_CLICK_JS = (
    "(() => { const b = Array.from(document.querySelectorAll('button, div[role=\"button\"]'))"
    ".find(el => /continue|allow|i agree/i.test(el.innerText || ''));"
    "if (b) { b.click(); return 'consent'; } return 'none'; })()"
)


class Tab:
    """One websocket to one page target, addressed by targetId."""

    def __init__(self, port: int, target_id: str, timeout: int = 30):
        listing = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=20).read())
        mine = next((t for t in listing
                     if t.get("id") == target_id and t.get("webSocketDebuggerUrl")), None)
        if mine is None:
            raise SafetyRefusal(f"target {target_id[:12]} has no debugger url on :{port}")
        self.ws = websocket.create_connection(mine["webSocketDebuggerUrl"],
                                              timeout=timeout, max_size=64 * 1024 * 1024)
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        want = self._id
        self.ws.send(json.dumps({"id": want, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.monotonic()))
            message = json.loads(self.ws.recv())
            if message.get("id") == want:
                if "error" in message:
                    raise SafetyRefusal(f"{method}: {message['error']}")
                return message.get("result") or {}
        raise SafetyRefusal(f"{method} timed out")

    def evaluate(self, expression: str) -> str:
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": False})
        return str((result.get("result") or {}).get("value") or "")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def current_urls(owner) -> dict[str, str]:
    return {t["id"]: t.get("url") or "" for t in tab_targets(owner)}


def navigate_and_settle(owner, target_id: str, url: str, wait: float) -> str:
    """Page.navigate on ONE target, then poll read-only target metadata until
    the URL settles.  No domain enable, no all-target attach, nothing killed."""
    tab = Tab(owner.port, target_id)
    try:
        tab.call("Page.navigate", {"url": url})
    finally:
        tab.close()
    deadline = time.monotonic() + wait
    last, stable = "", 0
    while time.monotonic() < deadline:
        time.sleep(1.5)
        now = current_urls(owner).get(target_id, "")
        if now == last and now:
            stable += 1
            if stable >= 2:
                return now
        else:
            stable, last = 0, now
    return last


def settle_only(owner, target_id: str, wait: float) -> str:
    """Poll a target after an in-flight click without issuing Page.navigate."""
    deadline = time.monotonic() + wait
    last, stable = "", 0
    while time.monotonic() < deadline:
        time.sleep(1.5)
        now = current_urls(owner).get(target_id, "")
        if now == last and now:
            stable += 1
            if stable >= 2:
                return now
        else:
            stable, last = 0, now
    return last


def probe(owner, target_id: str) -> dict:
    tab = Tab(owner.port, target_id)
    try:
        raw = tab.evaluate(PROBE_JS)
    finally:
        tab.close()
    try:
        return json.loads(raw)
    except ValueError:
        return {"url": "", "signedOut": True}


def evaluate_click(owner, target_id: str, expression: str) -> str:
    tab = Tab(owner.port, target_id)
    try:
        return tab.evaluate(expression)
    finally:
        tab.close()


def cookie_names(tab: Tab, url: str) -> list[str]:
    """Cookie NAME metadata only -- never values, never written anywhere."""
    try:
        res = tab.call("Network.getCookies", {"urls": [url]})
        return sorted({c.get("name", "") for c in res.get("cookies", [])})
    except Exception:
        return []


def capture_provider_evidence(owner, target_id: str, host: str) -> dict:
    """Read-only evidence snapshot of the provider surface the SSO landed on.

    Collects the final URL, lowercase body text (first 2500 chars), cookie-name
    metadata (names only, values never read or stored), and one screenshot.
    Classification still goes through signup_classify; nothing here infers
    signup, graduation, health, or capacity from the evidence alone.
    """
    evidence: dict = {"evidence": [], "authCookieNames": [], "bodyLow": ""}
    tab = Tab(owner.port, target_id)
    try:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        shot = tab.call("Page.captureScreenshot", {"format": "png"}).get("data")
        if shot:
            name = f"harness_{host.replace('.', '_')}_{int(time.time())}.png"
            (EVIDENCE / name).write_bytes(base64.b64decode(shot))
            evidence["evidence"].append(name)
        cookies = cookie_names(tab, f"https://{host}")
        evidence["authCookieNames"] = [n for n in cookies
                                       if any(k in n.lower() for k in
                                              ("token", "session", "auth", "jwt", "sid"))]
        evidence["cookieNameCount"] = len(cookies)
        evidence["bodyLow"] = tab.evaluate(
            "document.body ? document.body.innerText.slice(0, 2500).toLowerCase() : ''")
    except Exception as exc:
        evidence["degraded"] = f"{type(exc).__name__}"
    finally:
        tab.close()
    return evidence


def redirect_host_allowed(owner, source_host: str, url: str) -> bool:
    """Host-aware redirect validation.

    An OAuth redirect may only land back on the SOURCE provider's registered
    domain (registrable-domain comparison via tab_graduation_sweep.reg) or on
    accounts.google.com mid-flow. Any other host is rejected as a suspicious
    redirect (open-redirect/phishing guard) and reported, never followed.
    """
    if not url:
        return False
    hostname = (urllib.parse.urlsplit(url).hostname or "").lower()
    if not hostname:
        return False
    if hostname == "accounts.google.com":
        return True
    return reg(hostname) == reg(source_host)


def wait_for_google_popup(owner, exclude_id: str, wait: float) -> str | None:
    """Find the Google OAuth popup target produced by the SSO click, if any.

    Only page-type targets whose URL host is exactly accounts.google.com are
    eligible; any other new target is ignored. This is host-aware on purpose:
    an attacker-controlled or misconfigured provider redirect must never be
    mistaken for the Google OAuth surface. ``exclude_id`` skips the source tab.
    """
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        for t in tab_targets(owner):
            url = t.get("url") or ""
            if t.get("type") != "page" or t.get("id") == exclude_id:
                continue
            if (urllib.parse.urlsplit(url).hostname or "").lower() == "accounts.google.com":
                return t["id"]
        time.sleep(1.5)
    return None


def on_target_surface(current_url: str, target_url: str) -> bool:
    """Host-aware surface check: same registrable domain AND, when the target
    names a real path (e.g. /playground), the current path must be under it."""
    tgt = urllib.parse.urlsplit(target_url or "")
    cur = urllib.parse.urlsplit(current_url or "")
    if not tgt.hostname:
        return False
    want_path = (tgt.path or "").rstrip("/")
    cur_path = (cur.path or "").rstrip("/")
    if not reg(tgt.hostname) or reg(tgt.hostname) != reg(cur.hostname):
        return False
    return not want_path or cur_path.startswith(want_path)


def sso_pass(owner, target_id: str, url: str, wait: float,
             budget: float | None = None) -> dict:
    """Bounded Google-SSO attempt: navigate, probe, one Google-button click,
    one account-chooser click, one consent click.  Password/consent-walls that
    need more than that, hard walls, and classification all use the shared
    signup_classify taxonomy.  Nothing here captures, replays, graduates, or
    claims capacity.

    Bounded execution: ``budget`` (seconds) is a hard wall-clock cap. Every
    settle/poll re-checks it and returns early with ``BUDGET_EXCEEDED`` rather
    than running unbounded. Default budget scales with ``wait``.
    """
    if budget is None:
        budget = wait * 6 + 90.0
    deadline = time.monotonic() + budget

    def expired() -> bool:
        return time.monotonic() >= deadline

    def settle(target: str, cap: float) -> str:
        # Poll WITHOUT navigating: settle_only with the budget as a second cap.
        remaining = max(5.0, deadline - time.monotonic())
        return settle_only(owner, target, min(cap, remaining))

    source_host = (urllib.parse.urlsplit(url).hostname or "").lower()
    steps: list[str] = []
    outcome: dict = {"sso": "", "finalUrl": "", "steps": steps, "evidence": [],
                     "safeUrl": safe_url(url)}

    final = navigate_and_settle(owner, target_id, url, wait)
    if expired():
        outcome.update(sso="BUDGET_EXCEEDED", finalUrl=final)
        steps.append("budget exhausted after initial navigate")
        return outcome
    steps.append(f"landed {final[:80]}")

    state = probe(owner, target_id)
    if not state.get("signedOut"):
        # Already-authenticated before any SSO click: classify the pre-SSO
        # surface with the shared taxonomy. Never a new signup; the classifier's
        # own label is emitted verbatim (no local overrides).
        evidence = capture_provider_evidence(owner, target_id, source_host)
        pre = classify_pre_sso_surface(
            state.get("url") or final, evidence.get("bodyLow", ""),
            bool(evidence.get("authCookieNames")))
        steps.append(f"pre-sso classify={pre}")
        outcome.update(sso=pre,
                       finalUrl=state.get("url", final),
                       **{k: v for k, v in evidence.items() if k != "bodyLow"})
        return outcome

    clicked = evaluate_click(owner, target_id, GOOGLE_CLICK_JS)
    steps.append(f"google-button {clicked[:60]}")
    if expired():
        outcome.update(sso="BUDGET_EXCEEDED", finalUrl=final)
        return outcome
    if clicked == "none":
        outcome.update(sso="SSO_NO_GOOGLE_BUTTON", finalUrl=final)
        return outcome

    # The click may have started an in-flight redirect.  Never navigate the
    # original URL again here: doing so aborts OAuth before it reaches Google.
    final = settle(target_id, wait)
    here = urllib.parse.urlsplit(final)
    oauth_target = target_id
    if expired():
        outcome.update(sso="BUDGET_EXCEEDED", finalUrl=final)
        return outcome
    if "accounts.google.com" not in (here.hostname or ""):
        popup = wait_for_google_popup(owner, target_id,
                                      min(wait, max(5.0, deadline - time.monotonic())))
        if popup:
            oauth_target = popup
            steps.append(f"oauth popup target {popup[:12]}")
            final = settle(oauth_target, wait)
            here = urllib.parse.urlsplit(final)

    # Host-aware redirect validation: only accounts.google.com or the source
    # provider's own registrable domain may be followed. Anything else stops.
    if here.hostname and not redirect_host_allowed(owner, source_host, final):
        outcome.update(sso="WALL", finalUrl=final)
        steps.append(f"suspicious redirect host rejected: {here.hostname}")
        outcome["detail"] = "redirect landed on an unrelated host; not followed"
        return outcome
    if expired():
        outcome.update(sso="BUDGET_EXCEEDED", finalUrl=final)
        return outcome

    if "accounts.google.com" in (here.hostname or ""):
        path = (here.path or "").lower()
        if "chooser" in path or "oauthchooseaccount" in path:
            picked = evaluate_click(owner, oauth_target, CHOOSER_CLICK_JS)
            steps.append(f"chooser {picked[:60]}")
            if expired():
                outcome.update(sso="BUDGET_EXCEEDED", finalUrl=final)
                return outcome
            if picked == "none":
                outcome.update(sso="SSO_INITIATED", finalUrl=final,
                               detail="Google chooser was present but no account was selected")
                return outcome
            final = settle(oauth_target, wait)
            here = urllib.parse.urlsplit(final)
            path = (here.path or "").lower()
        if "signin/consent" in path or "oauthapprove" in path:
            # Bounded consent handling: ONE visible continue/allow click.
            consent = evaluate_click(owner, oauth_target, CONSENT_CLICK_JS)
            steps.append(f"consent {consent[:60]}")
            final = settle(oauth_target, wait)
            here = urllib.parse.urlsplit(final)
            if "accounts.google.com" in (here.hostname or ""):
                return {**outcome, "sso": "WALL", "finalUrl": final,
                        "detail": "Google consent wall still present after one "
                                  "bounded consent click; requires human review"}
        elif "signin" in path or "password" in path or "v3/signin" in path:
            # Password challenge: automation never types credentials.  The
            # profile's Google session should have prevented this; report it.
            return {**outcome, "sso": "WALL", "finalUrl": final,
                    "detail": "Google interactive authentication/password wall"}
    if expired():
        outcome.update(sso="BUDGET_EXCEEDED", finalUrl=final)
        return outcome

    # Re-validate post-flow: the surface must now be back on the provider's own
    # registrable domain. Still sitting on accounts.google.com means the SSO
    # never completed to a provider surface -- mid-flow evidence, SSO_INITIATED.
    if here.hostname and not redirect_host_allowed(owner, source_host, final):
        return {**outcome, "sso": "WALL", "finalUrl": final,
                "detail": f"redirect landed on unrelated host {here.hostname}; "
                          "not followed"}
    if "accounts.google.com" in (here.hostname or ""):
        return {**outcome, "sso": "SSO_INITIATED", "finalUrl": final,
                "detail": "Google flow did not redirect back to the provider "
                          "surface within budget"}

    # Final provider surface: capture evidence, hard-wall check, then classify
    # through signup_classify (never locally re-implemented).
    back_host = (here.hostname or source_host).lower()
    evidence = capture_provider_evidence(owner, oauth_target, back_host)
    if body_is_hard_wall(evidence.get("bodyLow", "")):
        steps.append("hard wall detected on provider surface")
        return {**outcome, "sso": "WALL", "finalUrl": final,
                "detail": "provider hard wall (verification/captcha/card/quota)",
                **{k: v for k, v in evidence.items() if k != "bodyLow"}}
    final_state = classify_final_provider_state(
        final, evidence.get("bodyLow", ""), bool(evidence.get("authCookieNames")))
    steps.append(f"final classify={final_state}")
    outcome.update(sso=final_state, finalUrl=final,
                   **{k: v for k, v in evidence.items() if k != "bodyLow"})
    return outcome


def plan_rows(manifest: dict) -> list[dict]:
    """One action per SITE (first tab wins); graduation dedupes by site anyway."""
    registry = {}
    for group in json.loads((STATE / "free_llm_chat_sites.json").read_text(encoding="utf-8")):
        for site in group.get("sites") or []:
            registry[site["name"]] = site.get("url") or ""

    seen, plan = set(), []
    for row in manifest["tabs"]:
        site = row.get("knownSite") or row.get("host") or ""
        if not site or site in seen:
            continue
        cls = row.get("classification")
        target_url = CHAT_SURFACE.get(site) or registry.get(site) or ""
        action = "NONE"
        if cls == "HARNESS_NAVIGATE":
            action = "VERIFY_OR_NAVIGATE"
        elif cls == "REQUIRES_NAVIGATION":
            action = "VERIFY_OR_NAVIGATE"
        elif cls == "SKIP_NOT_AUTHENTICATED":
            action = "SSO_ATTEMPT" if site in SSO_SITES else "REPORT_AUTH_WALL"
        elif cls == "UNSUITABLE_PAGE":
            action = "NAVIGATE" if target_url else "REPORT_SURFACE"
        elif cls == "UNMANAGED_TAB":
            action = "REGISTRY_PENDING"
        elif cls == "TRANSPORT_WEBSOCKET":
            action = "WEBSOCKET_ADAPTER_BUILD_TARGET"
        if action == "NONE" and not target_url:
            continue
        seen.add(site)
        plan.append({"site": site, "classification": cls, "action": action,
                     "targetId": row.get("targetId"), "from": row.get("url"),
                     "to": target_url})
    return plan


def print_plan(plan: list[dict]) -> None:
    for row in plan:
        print(f"  {row['action']:32} {row['site'][:26]:26} -> {row['to'][:60]}")


def apply_plan(plan: list[dict], owner, wait: float,
               budget: float | None = None) -> list[dict]:
    """Drive the plan row by row. Each row is failure-isolated: a stale target
    becomes TARGET_GONE, an unexpected row error becomes ROW_ERROR, and later
    rows continue. ``budget`` (seconds) is a hard wall-clock cap: once expired,
    remaining rows are marked BUDGET_EXCEEDED and are never driven."""
    results = []
    for row in plan:
        action, site = row["action"], row["site"]
        result = dict(row)
        if budget is not None and time.monotonic() >= budget:
            result.update(status="BUDGET_EXCEEDED")
            print(f"  {result['status']:24} {site[:30]}")
            results.append(result)
            continue
        row_wait = wait
        if budget is not None:
            row_wait = min(wait, max(5.0, budget - time.monotonic()))
        try:
            if action in ("VERIFY_OR_NAVIGATE", "NAVIGATE"):
                now = current_urls(owner).get(row["targetId"], "")
                if action == "VERIFY_OR_NAVIGATE" and on_target_surface(now, row["to"]):
                    result.update(status="ALREADY_ON_SURFACE", finalUrl=now)
                else:
                    final = navigate_and_settle(owner, row["targetId"], row["to"], row_wait)
                    result.update(status="NAVIGATED" if on_target_surface(final, row["to"])
                                  else "NAVIGATED_OFF_TARGET", finalUrl=final)
            elif action == "SSO_ATTEMPT":
                row_budget = (max(30.0, budget - time.monotonic())
                              if budget is not None else None)
                outcome = sso_pass(owner, row["targetId"], row["to"], wait, row_budget)
                label = outcome.pop("sso", "")
                if not sso_label_is_canonical(label):
                    raise ValueError(f"non-canonical SSO label emitted: {label!r}")
                result.update(status=label, **outcome)
            else:
                result.update(status="REPORTED_ONLY")
        except SafetyRefusal as exc:
            result.update(status="TARGET_GONE", error=str(exc))
        except Exception as exc:
            result.update(status="ROW_ERROR", error=f"{type(exc).__name__}: {exc}")
        # OAuth redirect URLs can carry credential-shaped query parameters;
        # redact query strings before anything reaches the report file.
        if result.get("finalUrl"):
            result["finalUrl"] = safe_url(result["finalUrl"])
        print(f"  {result['status']:24} {site[:30]}")
        results.append(result)
        time.sleep(1.0)
    return results


def refresh_readiness() -> bool:
    """Re-run the cookie-jar audit so SSO/navigation gains become verdicts."""
    try:
        done = subprocess.run([sys.executable, str(AUDIT)], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=300, check=False)
        tail = (done.stdout or "").strip().splitlines()[-3:]
        print("  readiness audit: " + " | ".join(tail))
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  readiness audit FAILED: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--apply", action="store_true",
                    help="navigate tabs and attempt bounded SSO (default: plan only)")
    ap.add_argument("--only", default="", help="substring filter on site name")
    ap.add_argument("--wait", type=float, default=25.0, help="settle seconds per navigation")
    ap.add_argument("--budget", type=float, default=900.0,
                    help="hard wall-clock budget in seconds for the whole --apply run")
    ap.add_argument("--no-audit", action="store_true",
                    help="skip the readiness re-audit after --apply")
    args = ap.parse_args()

    owner = assert_automation_seat(args.port)
    manifest = build_manifest(args.port)
    plan = plan_rows(manifest)
    if args.only:
        plan = [r for r in plan if args.only.lower() in r["site"].lower()]

    counts: dict[str, int] = {}
    for row in plan:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    print(f"tabs {manifest['summary']['pageTabs']}  harness actions {len(plan)}  {counts}\n")
    print_plan(plan)

    if not args.apply:
        print("\nplan only -- nothing was driven. Re-run with --apply to execute.")
        return 0

    results = apply_plan(plan, owner, args.wait,
                         budget=(time.monotonic() + max(5.0, args.budget))
                         if args.apply else None)
    REPORT.write_text(json.dumps({
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "port": args.port,
        "budgetSeconds": args.budget,
        "evidenceOnly": True,
        "capturesOrGraduates": False,
        "consumerContractUntouched": "http://127.0.0.1:8190/v1",
        "results": results}, indent=2) + "\n", encoding="utf-8")
    print(f"\nreport: {REPORT.relative_to(ROOT)}")

    if not args.no_audit:
        print("\nrefreshing seat readiness verdicts ...")
        refresh_readiness()
    print("\nnext: python scripts/automation/graduate_all_seats.py   (plan-only), then --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
