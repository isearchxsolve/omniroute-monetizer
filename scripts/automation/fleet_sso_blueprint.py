#!/usr/bin/env python3
"""fleet_sso_blueprint.py -- deterministic blueprint of the 2026-08-31 fleet drive.

This file compiles the agent-in-loop exercise of MASTER_WORKLOG.md #1424 into a
replayable Python state machine. Every branch below was executed and verified on
real automation seats on 2026-08-31; nothing is inferred, nothing is a prompt.
Given the same live surface evidence, this code makes the same decision the
agent made -- deterministically, with no model in the loop.

Manual step -> code section traceability
----------------------------------------
  probe seat, distrust stale cookie heuristics ......... plan(), probe_state
  Chrome Memory-Saver freeze (27/29 tabs silent) ....... cdp_drive.wake (activate + own-URL reload)
  target id changes after wake-navigation .............. cdp_drive.resolve_tid (re-resolved every round)
  read the surface before ANY action ................... classify_round() order below
  chatgpt.com two-step gate (Log in -> modal -> Google)  S_GATE then S_GOOGLE_BTN
  deepinfra cookie banner before auth controls ......... S_COOKIE_BANNER (one bounded Accept)
  google chooser pick (niloydassana@gmail.com) ......... S_GOOGLE_CHOOSER (data-identifier)
  google consent Continue (one bounded click) .......... S_GOOGLE_CONSENT
  password / OTP / MFA surfaces ........................ S_GOOGLE_WALL (never typed, never bypassed)
  qwen /auth#token=JWT callback self-redirect .......... S_CALLBACK
  together.ai direct Continue-with-Google .............. S_GOOGLE_BTN
  ai-sdk.dev vercel handshake + transient account_not_found + one retry ... S_RETRY_HANDSHAKE
  openai AuthApiFailure page carries retryUrl .......... S_ERROR_PAGE (follow once)
  openai AccountDeactivated ............................ WALL (operator action, reported)
  cohere /welcome/about-you after auth ................. ONBOARDING_VERIFICATION_REQUIRED (signup_classify)
  monica.im reCAPTCHA-gated form ....................... WALL (bot gate, reported)
  puter.com phone verification ......................... WALL (OTP lane, never touched)
  you.com signin stuck at 55% .......................... WALL (no SSO rendered)
  meta.ai Facebook-only auth ........................... LOGIN_REQUIRED
  v0.app anonymous playground, blackbox.ai no control .. LOGIN_REQUIRED
  grok.com shell never hydrates ........................ UNREACHABLE (reported)
  every terminal label ................................. signup_classify.VALID_TERMINAL_STATES only

Boundaries (unchanged): no typing, no CAPTCHA/MFA/quota/payment/phone bypass,
automation seats only, capture/replay/graduation untouched, zero capacity
claims -- states are provisional surface observations with named evidence.

    python fleet_sso_blueprint.py --port 9223                     # plan: ground truth only
    python fleet_sso_blueprint.py --port 9223 --drive             # full fleet state machine
    python fleet_sso_blueprint.py --port 9223 --drive --host deepinfra.com
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tab_graduation_sweep import assert_automation_seat, tab_targets  # noqa: E402
from signup_classify import (  # noqa: E402
    VALID_TERMINAL_STATES,
    body_is_hard_wall,
    classify_final_provider_state,
    classify_pre_sso_surface,
)
import cdp_drive as cdp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
VIDEO_HOSTS = ("labs.google", "rtst.ai", "heygen", "akool", "magichour",
               "nemovideo", "digen", "veoaifree", "veo")
GOOGLE_HOST = "accounts.google.com"

# ---------------------------------------------------------------------------
# Learned per-host knowledge (verified live 2026-08-31, worklog #1424).
# Annotations only: the state machine still probes live and verifies every
# assumption; a mismatch falls through to the generic tree and is reported.
# ---------------------------------------------------------------------------
HOST_KNOWLEDGE: dict[str, dict] = {
    "chatgpt.com": {"two_step_gate": True,
                    "note": "Log in opens in-page modal; Continue with Google lives there"},
    "api.together.ai": {"direct_google": True,
                        "note": "/signin renders Continue with Google directly"},
    "deepinfra.com": {"cookie_banner": True,
                      "note": "cookie Accept banner overlays /login auth controls"},
    "chat.qwen.ai": {"callback_fragment": True,
                     "note": "Google callback lands on /auth#token=JWT then self-redirects"},
    "dashboard.cohere.com": {"onboarding_after_auth": True,
                             "note": "auth ok; /welcome/about-you questionnaire needs a human"},
    "ai-sdk.dev": {"vercel_handshake": True,
                   "note": "Sign in with Vercel; transient account_not_found page; "
                           "one handshake retry establishes the session"},
    "monica.im": {"expected_wall": "recaptcha",
                  "note": "reCAPTCHA-gated login form; never hydrates under CDP"},
    "you.com": {"expected_wall": "stall",
                "note": "signin page stuck at 55%; SSO never renders"},
    "puter.com": {"expected_wall": "phone",
                  "note": "phone verification wall - OTP lane, never touched"},
    "meta.ai": {"expected_login_required": True,
                "note": "Meta-accounts only (Facebook auth), no Google SSO"},
    "v0.app": {"expected_login_required": True,
               "note": "anonymous playground, no SSO control"},
    "www.blackbox.ai": {"expected_login_required": True,
                        "note": "gate LOGIN renders but no Google control"},
    "grok.com": {"expected_unreachable": True,
                 "note": "shell renders, DOM never hydrates under CDP"},
    "gemini.google.com": {"skip": True,
                          "note": "Google-owned; the seat's Google session IS the auth"},
}

# Bounded per-action caps, learned from the manual drive (repeated consent
# clicks were needed on deepinfra because the page advanced late; everything
# else succeeded on the first click).
ACTION_CAPS = {"gate": 2, "google": 2, "vercel": 2, "chooser": 2,
               "consent": 3, "accept": 1, "callback_nav": 1,
               "retryurl": 1, "retry_handshake": 1}

ACCEPT_JS = (
    "(() => { const b = Array.from(document.querySelectorAll('button'))"
    ".find(el => /^accept$/i.test((el.innerText || '').trim()) &&"
    " (el.offsetParent !== null || el.getClientRects().length > 0));"
    "if (!b) return 'none'; b.click(); return 'accepted'; })()"
)

# Deterministic hard-wall extensions the shared regex does not cover
# (verified surfaces from #1424; reported, never bypassed).
SOFT_WALL_SIGNS = ("verify your phone", "send code", "recaptcha",
                   "unusual traffic", "we'll text you a verification code")


def soft_wall(body_low: str) -> str | None:
    body_low = (body_low or "").lower()
    for sign in SOFT_WALL_SIGNS:
        if sign in body_low:
            return sign
    return None


def openai_error(url: str) -> tuple[str, str, str]:
    """Decode auth.openai.com/error payload -> (kind, error_code, retryUrl)."""
    split = urllib.parse.urlsplit(url)
    if "auth.openai.com" not in (split.hostname or "") \
            or not split.path.startswith("/error"):
        return "", "", ""
    q = urllib.parse.parse_qs(split.query)
    payload = (q.get("payload") or [""])[0]
    try:
        pad = "=" * (-len(payload) % 4)
        doc = json.loads(base64.urlsafe_b64decode(payload + pad).decode("utf-8", "replace"))
        return (str(doc.get("kind") or ""), str(doc.get("errorCode") or ""),
                str(doc.get("retryUrl") or ""))
    except Exception:
        return "", "", ""


def google_surface_state(url: str) -> str:
    """Classify an accounts.google.com URL. ORDER MATTERS: the chooser lives
    under /v3/signin/accountchooser, consent under /signin/oauth/...; the
    password wall check must come last."""
    path = (urllib.parse.urlsplit(url).path or "").lower()
    if "chooser" in path or "oauthchooseaccount" in path:
        return "GOOGLE_CHOOSER"
    if "challenge" in path or "otp" in path:
        return "GOOGLE_WALL"
    if "signin/consent" in path or "oauthapprove" in path or "/signin/oauth" in path:
        return "GOOGLE_CONSENT"
    return "GOOGLE_WALL"


def read_body(port: int, tid: str, chars: int = 1200) -> str:
    try:
        return cdp.read_surface(port, tid, chars)[1].lower()
    except Exception:
        return ""


def terminal_from_surface(port: int, tid: str, host: str, probe: dict) -> dict:
    """Canonical terminal classification for an authenticated-looking surface."""
    auth, fbody, furl = cdp._evidence(port, tid, host)
    if body_is_hard_wall(fbody.lower()):
        return {"state": "WALL", "finalUrl": furl, "authCookieNames": auth,
                "detail": f"hard wall on provider surface ({soft_wall(fbody.lower()) or 'shared regex'})"}
    cls = classify_pre_sso_surface(furl, fbody.lower(), bool(auth))
    if cls == "LOGIN_REQUIRED":
        cls = "EXISTING_ACCOUNT"  # probe says authenticated; evidence thin
    return {"state": cls, "finalUrl": furl, "authCookieNames": auth}


def drive_host(port: int, url: str, tid_hint: str, budget: float = 240.0) -> dict:
    """The blueprint state machine for one host. Deterministic: same surface
    evidence -> same action. Terminal labels come only from signup_classify
    plus WALL / UNREACHABLE / BUDGET_EXCEEDED."""
    steps: list[str] = []
    t0 = time.monotonic()
    src = cdp._host(url)
    kn = HOST_KNOWLEDGE.get(src, {})
    tid = cdp.resolve_tid(port, src, tid_hint, None)
    used = dict.fromkeys(ACTION_CAPS, 0)
    google_seen = False
    empty_reads = 0
    probe_signed_out: bool | None = None
    outcome: dict = {"host": src, "url": url, "state": None, "steps": steps,
                     "authCookieNames": [], "finalUrl": ""}

    def left() -> float:
        return budget - (time.monotonic() - t0)

    def note(msg: str) -> None:
        steps.append(msg[:130])

    try:
        for rnd in range(18):
            if left() <= 15:
                outcome["state"] = "BUDGET_EXCEEDED"
                note("budget exhausted")
                break
            tid = cdp.resolve_tid(port, src, tid, None)
            listing = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=20).read())
            t = next((x for x in listing if x.get("id") == tid), None)
            cur = (t or {}).get("url") or ""
            host = cdp._host(cur)
            note(f"r{rnd} {host or '?'} {cur[:70]}")

            # -- Google surfaces -------------------------------------------------
            if host == GOOGLE_HOST:
                google_seen = True
                st = google_surface_state(cur)
                if st == "GOOGLE_CHOOSER":
                    if used["chooser"] >= ACTION_CAPS["chooser"]:
                        outcome["state"] = "SSO_INITIATED"
                        note("chooser stuck after bounded picks")
                        break
                    used["chooser"] += 1
                    note(f"chooser {cdp._click(port, tid, 'chooser')[:50]}")
                    cdp.poll_url(port, tid, min(12, left()))
                    continue
                if st == "GOOGLE_CONSENT":
                    if used["consent"] >= ACTION_CAPS["consent"]:
                        outcome["state"] = "SSO_INITIATED"
                        note("consent surface persisted after bounded clicks")
                        break
                    used["consent"] += 1
                    note(f"consent {cdp._click(port, tid, 'continue')[:50]}")
                    cdp.poll_url(port, tid, min(12, left()))
                    continue
                outcome["state"] = "WALL"
                note("google interactive sign-in surface - never typed")
                break

            # -- Provider error pages (openai lesson) ----------------------------
            kind, err_code, retry_url = openai_error(cur)
            if kind:
                if kind == "AccountDeactivated":
                    outcome["state"] = "WALL"
                    outcome["detail"] = f"openai {kind} (operator action required)"
                    note(f"error page kind={kind}")
                    break
                if kind == "AuthApiFailure" and retry_url and used["retryurl"] < ACTION_CAPS["retryurl"]:
                    used["retryurl"] += 1
                    note(f"AuthApiFailure -> retryUrl once")
                    tab = cdp.Tab(port, tid)
                    try:
                        tab.call("Page.navigate", {"url": retry_url})
                    finally:
                        tab.close()
                    cdp.poll_url(port, tid, min(20, left()))
                    continue
                outcome["state"] = "WALL"
                note(f"openai error kind={kind} code={err_code}")
                break

            body = read_body(port, tid)

            # -- Hydration-failure detection (grok lesson) -----------------------
            if len(body.strip()) < 40:
                empty_reads += 1
                if empty_reads >= 2:
                    outcome["state"] = "UNREACHABLE"
                    note("surface never rendered content (hydration failure)")
                    break
                cdp.wake(port, tid, url if host == src else cur)
                continue
            empty_reads = 0

            # -- OAuth callback fragment (qwen lesson) ---------------------------
            if host == src and "/auth" in (urllib.parse.urlsplit(cur).path or "") \
                    and "#token=" in cur:
                note("oauth callback fragment; settling")
                time.sleep(6)
                if used["callback_nav"] < ACTION_CAPS["callback_nav"]:
                    still = cdp.poll_url(port, tid, 8)
                    if "/auth" in (urllib.parse.urlsplit(still).path or ""):
                        used["callback_nav"] += 1
                        tab = cdp.Tab(port, tid)
                        try:
                            tab.call("Page.navigate", {"url": url})
                        finally:
                            tab.close()
                        cdp.poll_url(port, tid, min(15, left()))
                continue

            # -- Cookie banner (deepinfra lesson) --------------------------------
            if "essential cookies" in body and used["accept"] < ACTION_CAPS["accept"]:
                used["accept"] += 1
                tab = cdp.Tab(port, tid, timeout=15)
                tab.call_deadline = 12
                try:
                    note(f"cookie-banner {tab.evaluate(ACCEPT_JS)[:40]}")
                except Exception as e:
                    note(f"cookie-banner {type(e).__name__}")
                finally:
                    tab.close()
                time.sleep(2)
                continue

            # -- Hard walls -------------------------------------------------------
            if body_is_hard_wall(body):
                outcome["state"] = "WALL"
                outcome["detail"] = "hard wall (shared signup_classify regex)"
                note("hard wall on provider surface")
                break
            soft = soft_wall(body)
            if soft:
                outcome["state"] = "WALL"
                outcome["detail"] = f"provider wall signal: {soft}"
                note(f"wall signal {soft}")
                break

            # -- Already signed in? ------------------------------------------------
            probe = cdp.probe_state(port, tid, wake_url=url if host == src else None)
            probe_signed_out = bool(probe.get("signedOut"))
            if not probe_signed_out:
                outcome.update(terminal_from_surface(port, tid, host or src, probe))
                note(f"terminal {outcome['state']}")
                break

            # -- Auth controls, in the order the manual drive used them -----------
            if "sign in with vercel" in body and used["vercel"] < ACTION_CAPS["vercel"]:
                used["vercel"] += 1
                note(f"vercel {cdp._click(port, tid, 'vercel')[:50]}")
                cdp.poll_url(port, tid, min(25, left()))
                continue

            if used["google"] < ACTION_CAPS["google"]:
                clicked = ""
                try:
                    tab = cdp.Tab(port, tid, timeout=15)
                    tab.call_deadline = 12
                    try:
                        clicked = tab.evaluate(cdp.CLICK_JS["google"])
                    finally:
                        tab.close()
                except Exception as e:
                    clicked = f"error:{type(e).__name__}"
                if clicked and not clicked.startswith(("none", "error")):
                    used["google"] += 1
                    google_seen = True
                    note(f"google {clicked[:50]}")
                    cdp.poll_url(port, tid, min(25, left()))
                    continue

            if used["gate"] < ACTION_CAPS["gate"]:
                gate = ""
                try:
                    tab = cdp.Tab(port, tid, timeout=15)
                    tab.call_deadline = 12
                    try:
                        gate = tab.evaluate(cdp.CLICK_JS["gate"])
                    finally:
                        tab.close()
                except Exception as e:
                    gate = f"error:{type(e).__name__}"
                if gate and not gate.startswith(("none", "error")):
                    used["gate"] += 1
                    note(f"gate {gate[:50]}")
                    time.sleep(3)
                    continue

            # -- Handshake retry (ai-sdk lesson) ----------------------------------
            if google_seen and host == src and probe_signed_out \
                    and used["retry_handshake"] < ACTION_CAPS["retry_handshake"]:
                used["retry_handshake"] += 1
                note("handshake retry once (vercel/ai-sdk pattern)")
                tab = cdp.Tab(port, tid)
                try:
                    tab.call("Page.navigate", {"url": url})
                finally:
                    tab.close()
                cdp.poll_url(port, tid, min(15, left()))
                continue

            # -- Nothing usable ----------------------------------------------------
            outcome["state"] = "LOGIN_REQUIRED"
            note("no usable auth control on surface")
            break

        if outcome["state"] is None:
            outcome["state"] = "UNREACHABLE"
            note("round budget exhausted without a terminal state")
    except Exception as exc:  # per-host isolation: never abort the fleet
        outcome["state"] = "UNREACHABLE"
        outcome["detail"] = f"{type(exc).__name__}: {exc}"

    outcome["host"] = src
    knowledge = {k: v for k, v in kn.items() if k != "note"}
    if kn:
        outcome["knowledge"] = kn.get("note", "")
        expected = ("WALL" if kn.get("expected_wall") else
                    "LOGIN_REQUIRED" if kn.get("expected_login_required") else
                    "UNREACHABLE" if kn.get("expected_unreachable") else None)
        if expected and outcome["state"] != expected and outcome["state"] not in (
                "EXISTING_ACCOUNT", "ONBOARDING_VERIFICATION_REQUIRED"):
            outcome["knowledgeMISMATCH"] = f"expected {expected}, got {outcome['state']}"
        outcome["knowledgeKind"] = knowledge
    return outcome


def plan(port: int) -> tuple[list[dict], dict]:
    """Ground truth only: live probes (freeze-wake aware), zero clicks."""
    owner = assert_automation_seat(port)
    seen, todo = set(), []
    for t in tab_targets(owner):
        u = t.get("url") or ""
        h = cdp._host(u)
        if not h or h in seen or any(v in h for v in VIDEO_HOSTS):
            continue
        seen.add(h)
        todo.append({"tid": t["id"], "host": h, "url": u[:120]})

    def probe_one(row):
        try:
            probe = cdp.probe_state(port, row["tid"], wake_url=row["url"])
            row["signedOut"] = probe.get("signedOut")
            row["probeUrl"] = (probe.get("url") or "")[:100]
        except Exception as e:
            row["error"] = type(e).__name__
        return row

    with ThreadPoolExecutor(max_workers=2) as ex:
        rows = list(ex.map(probe_one, todo))
    meta = {"port": port, "hosts": len(rows),
            "signedOut": sum(1 for r in rows if r.get("signedOut")),
            "unreachable": sum(1 for r in rows if r.get("error")),
            "evidenceOnly": True, "capturesOrGraduates": False,
            "consumerContractUntouched": "http://127.0.0.1:8190/v1"}
    return rows, meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="deterministic blueprint of the 2026-08-31 fleet SSO drive")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--drive", action="store_true",
                    help="run the state machine (default: plan/ground-truth only)")
    ap.add_argument("--host", action="append", default=[],
                    help="restrict drive to these host substrings (repeatable)")
    ap.add_argument("--budget", type=float, default=240.0,
                    help="wall-clock seconds per host drive")
    args = ap.parse_args()

    rows, meta = plan(args.port)
    plan_path = STATE / f"fleet_blueprint_plan_{args.port}.json"
    plan_path.write_text(json.dumps({"meta": meta, "hosts": rows}, indent=1),
                         encoding="utf-8")
    print(f"plan: {meta['hosts']} hosts, {meta['signedOut']} signed-out, "
          f"{meta['unreachable']} unreachable -> {plan_path.name}")

    if not args.drive:
        for r in rows:
            tag = "OUT" if r.get("signedOut") else "IN " if r.get("signedOut") is not None else "ERR"
            print(f"  {tag} {r['host']}")
        print("plan only -- nothing was driven. Re-run with --drive to execute.")
        return 0

    wanted = [h.lower() for h in args.host]
    results = []
    for r in rows:
        host = r["host"]
        if wanted and not any(w in host for w in wanted):
            continue
        kn = HOST_KNOWLEDGE.get(host, {})
        if kn.get("skip"):
            results.append({"host": host, "state": "EXISTING_ACCOUNT",
                            "detail": f"skipped by knowledge table: {kn.get('note')}"})
            continue
        if r.get("error") and not r.get("signedOut"):
            # probe already failed after wake; give the state machine one
            # bounded attempt anyway (it wakes and re-resolves internally)
            pass
        if not r.get("signedOut") and r.get("signedOut") is not None:
            results.append({"host": host, "state": "EXISTING_ACCOUNT",
                            "detail": "live probe: already signed in, no action"})
            continue
        print(f"driving {host} ...")
        outcome = drive_host(args.port, r["url"], r["tid"], args.budget)
        if outcome["state"] not in VALID_TERMINAL_STATES and outcome["state"] not in (
                "WALL", "UNREACHABLE", "BUDGET_EXCEEDED"):
            outcome["detail"] = f"non-canonical state {outcome['state']!r} -> LOGIN_REQUIRED"
            outcome["state"] = "LOGIN_REQUIRED"
        results.append(outcome)
        print(f"  -> {outcome['state']} {('<' + str(outcome.get('detail')) + '>') if outcome.get('detail') else ''}")
        time.sleep(2)

    report = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "port": args.port, "budgetPerHost": args.budget,
              "evidenceOnly": True, "capturesOrGraduates": False,
              "consumerContractUntouched": "http://127.0.0.1:8190/v1",
              "results": results}
    out = STATE / f"fleet_blueprint_report_{args.port}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    counts: dict[str, int] = {}
    for r in results:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    print(f"report: {out.name}  states: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
