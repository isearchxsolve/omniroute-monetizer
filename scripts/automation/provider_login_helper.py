#!/usr/bin/env python3
"""
provider_login_helper.py -- one-time, human-driven sign-in for the ROBOT's own browser.

WHY THIS FILE EXISTS
--------------------
The 2026-08-22 incident: automation opened the operator's LIVE Chrome profile to reuse a
login. Chrome binds a signed-in session to one browser instance (Device Bound Session
Credentials); when a different browser presents that session, Google REVOKES it server-side.
The operator was silently logged out of all four accounts, repeatedly, for days.

So automation may never open the operator's Chrome. But that does not end browser work,
because there is a real distinction:

    COPYING an existing login into another browser  -> fatal, revokes the session.
    Creating a NEW login inside another browser     -> normal, like adding a second device.

This script does the second thing, once, with the human present:

    1. Launch installed Chrome against the ROBOT's own empty profile
       (state/automation_profiles/providers -- never the operator's).
    2. Walk the operator through each provider site. They sign in BY HAND.
    3. Cookies persist in the robot's profile, so every later automated run reuses them
       without a human and without ever touching the operator's browser.

The operator does NOT need to close their own Chrome: a separate user-data-dir is a
separate Chrome instance, and ProcessSingleton locks are per-user-data-dir.

WHAT THIS SCRIPT NEVER DOES
---------------------------
* Never reads, copies, opens, or aliases the operator's Chrome profile.
* Never types, stores, or logs a password, token, cookie value, or API key.
* Never clicks through a captcha or a 2FA prompt on the operator's behalf.
* Never claims "signed in" -- it reports PROVIDER_SESSION_AUTHENTICATED or
  LOGIN_WALL for a specific site, which is a different and checkable claim.

See AGENTS.md items 5 and 14, CHROME_RULES.md, MASTER_WORKLOG.md #1017-#1030.

USAGE
-----
    python provider_login_helper.py                 # interactive walkthrough (default)
    python provider_login_helper.py --status        # read-only: which sites are logged in
    python provider_login_helper.py --only kie,segmind
    python provider_login_helper.py --google        # optional: sign into Google first so
                                                    # saved passwords autofill the rest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chrome_live_guard import (  # noqa: E402  (path bootstrap must come first)
    LiveProfileRefused,
    assert_safe,
    install,
    is_refusal,
    safe_profile_dir,
)

PROJECT_ROOT = HERE.parents[1]
PROFILE_TAG = "providers"
REPORT = PROJECT_ROOT / "state" / "harvest" / "login_status.json"

# ---------------------------------------------------------------------------------------
# Targets. `tier` explains WHY a provider is worth the operator's time, so nobody re-argues
# it later. Model counts are OmniRoute registry counts as of 2026-08-22.
# ---------------------------------------------------------------------------------------

TARGETS = [
    {
        "name": "kie",
        "omniroute_provider": "kie",
        "models": 16,
        "url": "https://kie.ai/api-key",
        "signin": "email+password, or Google button",
        "tier": "DO -- biggest single win, 16 models",
        "markers": ["api key", "credits", "dashboard"],
    },
    {
        "name": "segmind",
        "omniroute_provider": "segmind",
        "models": 5,
        "url": "https://cloud.segmind.com/console/api-keys",
        "signin": "email+password",
        "tier": "DO -- plain email signup, no Google needed",
        "markers": ["api key", "console", "credits"],
    },
    {
        "name": "novita",
        "omniroute_provider": "novita",
        "models": 2,
        "url": "https://novita.ai/settings/key-management",
        "signin": "email+password, or Google button",
        "tier": "DO -- plain email signup, no Google needed",
        "markers": ["key management", "api key", "settings"],
    },
    {
        "name": "aistudio",
        "omniroute_provider": "vertex",
        "models": 3,
        "url": "https://aistudio.google.com/apikey",
        "signin": "Google account -- BLOCKED in this browser, use PasteAKey.cmd",
        "tier": "PASTE ONLY -- Google refuses automated browsers; copy the key by hand",
        "markers": ["create api key", "google ai studio", "api keys"],
        "paste_only": True,
    },
    {
        "name": "leonardo",
        "omniroute_provider": "leonardo",
        "models": 1,
        "url": "https://app.leonardo.ai/api-access",
        "signin": "email+password (avoid the Google button -- it will be refused)",
        "tier": "MAYBE -- their API tier may demand a card; stop if it does",
        "markers": ["api access", "api key", "tokens"],
    },
]

DROPPED = [
    ("haiper", "their API-key page is a dead link (404). 1 model. Not worth chasing."),
    ("runwayml", "OmniRoute has 0 models wired for it, so a key buys nothing today."),
    ("deepinfra", "already rejected: account has no funds, and funds are out of scope."),
]

GOOGLE_STEP = {
    "name": "google",
    "url": "https://accounts.google.com/",
    "why": "Signing into Google here syncs your SAVED PASSWORDS into the robot's browser, "
    "so the provider logins below autofill instead of you typing them.",
}

# Measured 2026-08-22: Google refuses sign-in in a Playwright-launched Chrome with
# "Couldn't sign you in / This browser or app may not be secure". Playwright starts Chrome
# with automation switches and navigator.webdriver set, and Google rejects that outright.
#
# We do NOT try to disguise it. Defeating that check is exactly the class of trick that gets
# an account flagged, and this operator's accounts have already been damaged once. A Google
# login wall is a CORRECT, REPORTABLE outcome -- and for API keys it is not even a blocker,
# because the operator can copy a key by hand in their own Chrome (PasteAKey.cmd) and the
# automation then uses the key over plain HTTP with no browser at all.
GOOGLE_BLOCK_MARKERS = (
    "couldn't sign you in",
    "couldn’t sign you in",
    "this browser or app may not be secure",
    "browser or app may not be secure",
)
GOOGLE_BLOCKED = "BLOCKED_BY_GOOGLE_AUTOMATION_POLICY"

# Generic evidence that a page is past the login wall.
SIGNED_IN_MARKERS = ("sign out", "log out", "logout", "my account")
# Generic evidence that a page IS the login wall.
LOGIN_WALL_MARKERS = ("sign in", "log in", "continue with google", "create account", "password")

BANNER_HTML = """
<!doctype html><meta charset="utf-8">
<style>
  body{{font:16px/1.6 system-ui,Segoe UI,sans-serif;margin:0;background:#0d1117;color:#e6edf3}}
  .wrap{{max-width:720px;margin:8vh auto;padding:0 28px}}
  h1{{font-size:26px;margin:0 0 6px}}
  .tag{{display:inline-block;background:#1f6feb;color:#fff;padding:3px 10px;border-radius:20px;
       font-size:12px;letter-spacing:.08em;text-transform:uppercase}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin:22px 0}}
  ol{{padding-left:22px}} li{{margin:8px 0}}
  .muted{{color:#8b949e;font-size:14px}}
  code{{background:#21262d;padding:2px 6px;border-radius:4px;font-size:14px}}
</style>
<div class="wrap">
  <span class="tag">Robot's browser</span>
  <h1>This window is not your Chrome.</h1>
  <p>It is a separate, empty browser that belongs to the automation. Your own Chrome and
     your own logins are untouched by anything that happens here.</p>
  <div class="card">
    <ol>
      <li>A provider website will open in the tab next to this one.</li>
      <li>Sign in there by hand, the normal way.</li>
      <li>Go back to the black text window and press <code>Enter</code>.</li>
    </ol>
  </div>
  <p class="muted">If a site asks for a credit card, or shows a captcha you cannot pass,
     that is a stop sign. Type <code>s</code> instead of pressing Enter and we skip it.</p>
  <p class="muted">You only do this once per site. After that the automation reuses this
     browser on its own.</p>
</div>
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def _classify(page, markers) -> str:
    """Return PROVIDER_SESSION_AUTHENTICATED | LOGIN_WALL | UNCLEAR, or the Google block.

    Deliberately conservative. UNCLEAR is an honest answer and is preferred over guessing;
    the operator is standing right there and can overrule it.
    """
    try:
        body = (page.inner_text("body", timeout=8000) or "").lower()
    except Exception:
        return "UNCLEAR"

    if not body.strip():
        return "UNCLEAR"

    # Checked first: this page looks like a login wall, but it is a categorically different
    # thing. No amount of correct typing gets past it, so never report it as LOGIN_WALL.
    if any(m in body for m in GOOGLE_BLOCK_MARKERS):
        return GOOGLE_BLOCKED

    site_hit = any(m in body for m in markers)
    generic_hit = any(m in body for m in SIGNED_IN_MARKERS)
    wall_hit = any(m in body for m in LOGIN_WALL_MARKERS)

    if site_hit or generic_hit:
        # A dashboard that also renders a "sign in" string in a footer is common; site
        # markers win over the generic wall markers.
        return "PROVIDER_SESSION_AUTHENTICATED"
    if wall_hit:
        return "LOGIN_WALL"
    return "UNCLEAR"


def _open_browser(pw, headed: bool = True):
    """Persistent context on the ROBOT's profile. Guard-checked twice, on purpose."""
    udd = safe_profile_dir(PROFILE_TAG)
    assert_safe(udd, who="provider_login_helper")
    _say("ok", f"robot's own browser profile: {udd}")

    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(udd),
        channel="chrome",
        headless=not headed,
        viewport=None,
        args=["--window-size=1280,900", "--window-position=60,40", "--no-first-run"],
    )
    return ctx


def _board(ctx):
    """Tab 0 is a standing instruction board, so the window itself explains itself."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.set_content(BANNER_HTML)
    except Exception:
        pass
    return page


def run_status(only: list[str] | None) -> int:
    """Read-only: report what the robot's profile is already logged into."""
    from playwright.sync_api import sync_playwright

    targets = [t for t in TARGETS if not only or t["name"] in only]
    results = {}

    with sync_playwright() as pw:
        install()
        ctx = _open_browser(pw, headed=True)
        _board(ctx)
        page = ctx.new_page()
        try:
            for t in targets:
                try:
                    page.goto(t["url"], timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(6000)  # SPA dashboards paint a shell first
                    state = _classify(page, t["markers"])
                except Exception as exc:
                    state = "UNCLEAR"
                    _say("PROBLEM", f"{t['name']}: could not load page ({type(exc).__name__})")
                results[t["name"]] = state
                mark = "ok" if state == "PROVIDER_SESSION_AUTHENTICATED" else "YOU"
                _say(mark, f"{t['name']:<10} {state}")
        finally:
            ctx.close()

    _write_report(results, mode="status")
    return 0


def run_interactive(only: list[str] | None, do_google: bool) -> int:
    from playwright.sync_api import sync_playwright

    targets = [t for t in TARGETS if not only or t["name"] in only]
    results = {}

    print()
    print("=" * 74)
    print("  ONE-TIME PROVIDER SIGN-IN")
    print("=" * 74)
    print()
    print("  A browser window is about to open. It is NOT your Chrome -- it is a")
    print("  separate empty browser that belongs to the automation.")
    print()
    print("  Your own Chrome, and your own Google logins, are not touched.")
    print("  You do not need to close your own Chrome.")
    print()
    print("  For each site: sign in in that window, then come back here and press Enter.")
    print("  If a site wants a credit card, or shows a captcha you cannot pass, type 's'")
    print("  and we skip it and record why.")
    print()
    input("  Press Enter to open the browser... ")
    print()

    with sync_playwright() as pw:
        install()
        try:
            ctx = _open_browser(pw, headed=True)
        except LiveProfileRefused as exc:
            _say("PROBLEM", "the guard refused the profile path. That means this script is")
            _say("PROBLEM", "wrong, not the guard. Nothing was opened. Details below.")
            print(exc)
            return 2

        _board(ctx)
        page = ctx.new_page()

        try:
            if do_google:
                print("-" * 74)
                _say("info", "OPTIONAL STEP: Google sign-in")
                _say("YOU", "MEASURED 2026-08-22: Google REFUSES this. You will get")
                _say("YOU", "\"Couldn't sign you in / This browser or app may not be secure\".")
                _say("YOU", "Playwright starts Chrome in a controlled mode and Google rejects")
                _say("YOU", "sign-ins from it. We do not disguise that. Recommend: skip.")
                print(f"       (If it ever starts working: {GOOGLE_STEP['why']})")
                print()
                choice = input("       Type 'y' to try anyway, anything else skips: ")
                if choice.strip().lower() == "y":
                    try:
                        page.goto(GOOGLE_STEP["url"], timeout=60000,
                                  wait_until="domcontentloaded")
                    except Exception as exc:
                        _say("PROBLEM", f"could not open Google ({type(exc).__name__})")
                    input("       Try it in the browser window, then press Enter here... ")
                    state = _classify(page, ["google account", "manage your"])
                    results["google"] = state
                    if state == GOOGLE_BLOCKED:
                        _say("YOU", "Confirmed: Google blocked it, as expected. Moving on.")
                    else:
                        _say("info", f"google: {state}")
                else:
                    results["google"] = "SKIPPED_BLOCKED_BY_GOOGLE_POLICY"
                    _say("ok", "Skipped. You will type provider passwords by hand instead.")

            for i, t in enumerate(targets, 1):
                print()
                print("-" * 74)
                print(f"  {i} of {len(targets)}:  {t['name'].upper()}"
                      f"   ({t['models']} models in OmniRoute)")
                print(f"       sign-in : {t['signin']}")
                print(f"       why     : {t['tier']}")
                print(f"       page    : {t['url']}")
                print()

                if t.get("paste_only"):
                    _say("YOU", "Skipping this one on purpose. Google will not accept a")
                    _say("YOU", "sign-in from this browser, and disguising it is not something")
                    _say("YOU", "we do. Get this key by hand instead: open the page in YOUR")
                    _say("YOU", "own Chrome, copy the key, then run PasteAKey.cmd.")
                    results[t["name"]] = "PASTE_REQUIRED_GOOGLE_ONLY_SITE"
                    continue

                try:
                    page.goto(t["url"], timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                except Exception as exc:
                    _say("PROBLEM", f"page would not load ({type(exc).__name__}). "
                                    "Try it by hand in the window, or type 's'.")

                before = _classify(page, t["markers"])
                if before == "PROVIDER_SESSION_AUTHENTICATED":
                    _say("ok", "already signed in from a previous run -- nothing for you to do.")
                    results[t["name"]] = before
                    continue

                ans = input("       Sign in in the browser, then press Enter"
                            " (or 's' to skip): ").strip().lower()
                if ans == "s":
                    reason = input("       One line: what blocked you? ").strip()
                    results[t["name"]] = f"SKIPPED: {reason or 'no reason given'}"
                    _say("YOU", f"{t['name']}: skipped -- {reason or 'no reason given'}")
                    continue

                try:
                    page.wait_for_timeout(2500)
                    after = _classify(page, t["markers"])
                except Exception:
                    after = "UNCLEAR"

                results[t["name"]] = after
                if after == "PROVIDER_SESSION_AUTHENTICATED":
                    _say("ok", f"{t['name']}: PROVIDER_SESSION_AUTHENTICATED "
                               "(this page is past the login wall)")
                elif after == GOOGLE_BLOCKED:
                    _say("YOU", f"{t['name']}: Google refused the sign-in because this is an")
                    _say("YOU", "automated browser. If this site offers email+password, use")
                    _say("YOU", "that instead. Otherwise get the key by hand: PasteAKey.cmd.")
                elif after == "LOGIN_WALL":
                    _say("YOU", f"{t['name']}: still looks like a login page. "
                                "The automation will report this as a login wall.")
                else:
                    _say("info", f"{t['name']}: UNCLEAR -- I could not tell. Not claiming "
                                 "either way. The harvester will find out for real.")

            print()
            print("-" * 74)
            _say("ok", "Done. Closing the robot's browser. Its cookies stay in its own")
            _say("ok", "profile folder, so the automation can reuse them without you.")
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    _write_report(results, mode="interactive")
    _summary(results)
    return 0


def _write_report(results: dict, mode: str) -> None:
    """Persist states only. There is nothing secret in here, and that is deliberate."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now(),
        "mode": mode,
        "profile": str(safe_profile_dir(PROFILE_TAG)),
        "note": "States only. No passwords, cookies, tokens or API keys are ever stored here.",
        "results": results,
        "dropped": {name: why for name, why in DROPPED},
    }
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _say("info", f"wrote {REPORT}")


def _summary(results: dict) -> None:
    ready = [k for k, v in results.items() if v == "PROVIDER_SESSION_AUTHENTICATED"]
    paste = [k for k, v in results.items()
             if v == GOOGLE_BLOCKED or v.startswith("PASTE_REQUIRED")]
    blocked = [(k, v) for k, v in results.items() if v.startswith("SKIPPED")
               or v == "LOGIN_WALL"]
    unclear = [k for k, v in results.items() if v == "UNCLEAR"]

    print()
    print("=" * 74)
    print("  RESULT")
    print("=" * 74)
    if ready:
        print(f"  Signed in and ready for automation : {', '.join(sorted(ready))}")
    if paste:
        print(f"  Get the key by hand (PasteAKey.cmd): {', '.join(sorted(paste))}")
        print("      Google will not accept an automated browser. Open the page in YOUR")
        print("      own Chrome, copy the key, and paste it once. Nothing automated goes")
        print("      near your Chrome -- you do the copying.")
    if unclear:
        print(f"  Could not tell (not claiming)      : {', '.join(sorted(unclear))}")
    for name, why in blocked:
        print(f"  Blocked                            : {name} -- {why}")
    if not ready and not paste:
        print("  Nothing is signed in yet.")
    print()
    print("  What is NOT claimed: that any API key exists or works. Signing in is step 1.")
    print("  A key only counts once it returns HTTP 200 from the provider's own endpoint.")
    print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true",
                    help="read-only: report which sites the robot's profile is logged into")
    ap.add_argument("--only", default="",
                    help="comma-separated subset, e.g. kie,segmind")
    ap.add_argument("--google", action="store_true",
                    help="offer an optional Google sign-in first so saved passwords autofill")
    args = ap.parse_args(argv)

    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    if only:
        known = {t["name"] for t in TARGETS}
        unknown = [s for s in only if s not in known]
        if unknown:
            _say("PROBLEM", f"unknown target(s): {', '.join(unknown)}")
            _say("info", f"known targets: {', '.join(sorted(known))}")
            return 2

    try:
        import playwright  # noqa: F401
    except ImportError:
        _say("PROBLEM", "Playwright is not installed in this Python. Nothing was opened.")
        _say("info", "Use the hermes venv interpreter, which has it.")
        return 3

    try:
        if args.status:
            return run_status(only)
        return run_interactive(only, do_google=args.google)
    except LiveProfileRefused as exc:
        _say("PROBLEM", "REFUSED by chrome_live_guard. The guard is right; this code is wrong.")
        print(exc)
        return 2
    except KeyboardInterrupt:
        print()
        _say("info", "stopped by operator. Nothing was changed in your own Chrome.")
        return 130
    except Exception as exc:
        # A refusal raised by the machine-wide bootstrap copy of the guard used to slip past
        # the handler above (two module identities, two exception classes). is_refusal() is
        # identity-independent, so a refusal can never be misreported as a generic crash.
        if is_refusal(exc):
            _say("PROBLEM", "REFUSED by chrome_live_guard. The guard is right; "
                            "this code is wrong.")
            print(exc)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
