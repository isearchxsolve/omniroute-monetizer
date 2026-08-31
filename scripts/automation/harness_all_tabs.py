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
                        live).  A password wall or OAuth consent screen is a
                        reportable outcome -- never typed, never bypassed.
  UNSUITABLE_PAGE       navigate away from cookie-mismatch / get-started pages
  UNMANAGED_TAB         report only (registry additions are a separate edit)
  VIDEO_SEPARATE_GRADUATION / TRANSPORT_WEBSOCKET  listed, never touched

Modality note (operator, 2026-08-29): most chat providers ALSO carry video
models.  Graduating the chat surface does not exhaust a seat's value; video
graduation stays a separate spend-gated lane and is only recorded here.

Nothing here captures, replays, or graduates.  After this pass re-run
`graduate_all_seats.py` (plan-only) to see the new funnel, then `--apply`.

    python harness_all_tabs.py                 # plan only -- drives nothing
    python harness_all_tabs.py --apply         # navigate + bounded SSO clicks
    python harness_all_tabs.py --apply --only groq
"""
from __future__ import annotations

import argparse
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
    tab_targets,
)
from signup_classify import (  # noqa: E402
    classify_final_provider_state,
    classify_pre_sso_surface,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
REPORT = STATE / "tab_harness_report.json"
AUDIT = pathlib.Path(__file__).resolve().parent / "seat_readiness_audit.py"

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


def sso_pass(owner, target_id: str, url: str, wait: float) -> dict:
    """Bounded Google-SSO attempt: navigate, probe, one Google-button click,
    one account-chooser click.  Password/consent walls stop and are reported."""
    steps: list[str] = []
    final = navigate_and_settle(owner, target_id, url, wait)
    state = probe(owner, target_id)
    steps.append(f"landed {final[:80]}")
    if not state.get("signedOut"):
        return {"sso": "already_signed_in", "finalUrl": final, "steps": steps}

    clicked = evaluate_click(owner, target_id, GOOGLE_CLICK_JS)
    steps.append(f"google-button {clicked[:60]}")
    if clicked == "none":
        return {"sso": "NO_GOOGLE_BUTTON", "finalUrl": final, "steps": steps}

    # The click may have started an in-flight redirect.  Never navigate the
    # original URL again here: doing so aborts OAuth before it reaches Google.
    final = settle_only(owner, target_id, wait)
    here = urllib.parse.urlsplit(final)
    oauth_target = target_id
    if "accounts.google.com" not in (here.hostname or ""):
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            google = next((t for t in tab_targets(owner)
                           if t.get("type") == "page" and
                           "accounts.google.com" in (t.get("url") or "")), None)
            if google:
                oauth_target = google["id"]
                final = settle_only(owner, oauth_target, wait)
                here = urllib.parse.urlsplit(final)
                break
            time.sleep(1.5)
    if "accounts.google.com" in (here.hostname or ""):
        path = (here.path or "").lower()
        if "chooser" in path or "oauthchooseaccount" in path:
            picked = evaluate_click(owner, oauth_target, CHOOSER_CLICK_JS)
            steps.append(f"chooser {picked[:60]}")
            if picked == "none":
                return {"sso": "SSO_INITIATED", "finalUrl": final, "steps": steps,
                        "detail": "Google chooser was present but no account was selected"}
            final = settle_only(owner, oauth_target, wait)
        elif "signin" in path or "password" in path or "v3/signin" in path:
            # Password challenge: automation never types credentials.  The
            # profile's Google session should have prevented this; report it.
            return {"sso": "WALL", "finalUrl": final, "steps": steps,
                    "detail": "Google interactive authentication/password wall"}
        elif "signin/consent" in path or "oauthapprove" in path:
            return {"sso": "WALL", "finalUrl": final, "steps": steps,
                    "detail": "Google consent wall requires bounded human review"}

    state = probe(owner, target_id)
    verdict = ("LOGIN_REQUIRED" if state.get("signedOut")
               else "EXISTING_ACCOUNT")
    steps.append(f"verdict {verdict} @ {state.get('url', '')[:80]}")
    return {"sso": verdict, "finalUrl": state.get("url", final), "steps": steps}


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


def apply_plan(plan: list[dict], owner, wait: float) -> list[dict]:
    results = []
    for row in plan:
        action, site = row["action"], row["site"]
        result = dict(row)
        try:
            if action in ("VERIFY_OR_NAVIGATE", "NAVIGATE"):
                now = current_urls(owner).get(row["targetId"], "")
                if action == "VERIFY_OR_NAVIGATE" and now.startswith(row["to"]):
                    result.update(status="ALREADY_ON_SURFACE", finalUrl=now)
                else:
                    final = navigate_and_settle(owner, row["targetId"], row["to"], wait)
                    result.update(status="NAVIGATED" if final.startswith(row["to"])
                                  else "NAVIGATED_OFF_TARGET", finalUrl=final)
            elif action == "SSO_ATTEMPT":
                outcome = sso_pass(owner, row["targetId"], row["to"], wait)
                result.update(status=outcome.pop("sso"), **outcome)
            else:
                result.update(status="REPORTED_ONLY")
        except SafetyRefusal as exc:
            result.update(status="TARGET_GONE", error=str(exc))
        except Exception as exc:
            result.update(status="ROW_ERROR", error=f"{type(exc).__name__}: {exc}")
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

    results = apply_plan(plan, owner, args.wait)
    REPORT.write_text(json.dumps({
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "port": args.port, "results": results}, indent=2) + "\n", encoding="utf-8")
    print(f"\nreport: {REPORT.relative_to(ROOT)}")

    if not args.no_audit:
        print("\nrefreshing seat readiness verdicts ...")
        refresh_readiness()
    print("\nnext: python scripts/automation/graduate_all_seats.py   (plan-only), then --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
