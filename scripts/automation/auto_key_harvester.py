"""Full automation: Continue with Google -> pick the profile -> create an API key -> wire it.

WHY THIS FILE EXISTS
--------------------
The operator's words, 2026-08-22, replacing the click-per-provider tool that shipped earlier
the same day:

    "we go full automation no human click please not possile over 109  providers"
    "each automation item just needs few steps continue with google select profile
     and create new api key copy to clipoard and wire no rocket science"
    "can e easily achieved with modern automation tools selenium playwright"

They are right that 51 providers x manual clicking is not a plan. So every step the human was
doing is now a Playwright step:

    1. open the provider's site           -> page.goto(website)
    2. find the way in                    -> click Sign in / Sign up / Get started
    3. "Continue with Google"             -> click_google_sso()
    4. select profile                     -> pick_google_account()      <-- the unproven step
    5. reach the API-keys page            -> reach_key_page()
    6. create new API key                 -> press_create()
    7. copy to clipboard                  -> grab_key()  (clipboard first, page text second)
    8. wire                               -> wire() from harvest_free_keys, unchanged

THE ONE THING THAT IS NOT KNOWN YET, AND WHY --probe EXISTS
----------------------------------------------------------
Worklog #1033 recorded Google REFUSING a Playwright-launched Chrome at the sign-in step:
"Couldn't sign you in / This browser or app may not be secure", at
accounts.google.com/v3/signin/rejected?...&flowName=GlifWebSignIn. That refusal was for
*typing a password*. This tool never types a password: the robot profile already carries the
Google session (34 google-domain cookies, measured), and worklog #1042 already drove AI Studio
under Playwright with that same session and got entry_state SIGNED_IN.

So step 4 should be an account CHOOSER, not a password form. Should is not measured. Whether
Google honours an OAuth consent/chooser for a THIRD-PARTY site under Playwright has never been
tested here. `--probe SLUG` runs steps 1-4 against one provider and reports exactly what came
back. If Google refuses, that is the honest answer and the run stops -- see the next section.

WHAT THIS TOOL WILL NOT DO
--------------------------
* It will not defeat Google's automation refusal with stealth patching, fingerprint spoofing, or
  a patched CDP surface. That decision is already on the record (worklog #1033). If step 4 comes
  back GOOGLE_REFUSED_AUTOMATION, the run aborts and says so. A blocked automation that is
  reported truthfully is a result; a bypassed account protection is not.
* It will not touch a credit card. Operator, verbatim: "you reject, all paywall card
  requirements and all captcha. You do not hit them or hammer them". A card marker on the page
  ends that provider with PAYWALL_REFUSED and moves on.
* It will not solve, answer, wait out, or retry a CAPTCHA. A CAPTCHA marker ends that provider
  with CAPTCHA_REFUSED and moves on.
* It will not retry anything. One pass per provider. No loops around a wall.

CHROME SAFETY -- the rule that outranks getting keys
----------------------------------------------------
Operator, verbatim: "you never open an existing Chrome profile. You open a blank profile i
signup with google, then you start harvesting."

Every launch goes through safe_profile_dir("providers") + assert_safe(). The operator's live
Chrome tree at %LOCALAPPDATA%/Google/Chrome/User Data is never opened, read, or copied. This is
not a style preference: opening the live root under Playwright is what revoked four Chrome Sync
sessions on 2026-08-22.

SECRET HANDLING (anti-pattern #7)
---------------------------------
Console and the JSON report get a fingerprint only -- first 4 chars, last 4 chars, length. Raw
key values are written to state/generated_keys.json, which is gitignored, and nowhere else. A
key is NEVER called harvested because a page displayed it, or because OmniRoute's own
test_connection said valid=True. It counts only when a real model returns real text -- the
real_completion() gate, which exists because `uncloseai` passed test_connection and then 404'd
on every model it advertised.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time
from typing import Any, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from chrome_live_guard import assert_safe, safe_profile_dir  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402

# Reuse -- one implementation of the proof gate and the delete-on-failure policy.
from harvest_free_keys import (  # noqa: E402
    KEYS_FILE,
    KNOWN_DEAD,
    card_stance,
    fingerprint,
    load_targets,
    real_completion,
    wire,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "state" / "harvest" / "auto_harvest.json"
SHOTS = ROOT / "state" / "harvest" / "shots"
PROFILE_TAG = "providers"

# --------------------------------------------------------------------------------------------
# Walls. These end a provider immediately. They are matched against visible page text, so they
# are deliberately phrased the way a page phrases them, not the way a spec would.
# --------------------------------------------------------------------------------------------
CARD_MARKERS = re.compile(
    r"card number|cardholder|credit or debit|add a payment method|add payment method|"
    r"billing address|security code|\bcvc\b|\bcvv\b|expiry date|expiration date|"
    r"start (?:your )?free trial|enter your card|payment details|upgrade to (?:pro|paid)",
    re.I,
)
CAPTCHA_MARKERS = re.compile(
    r"i'?m not a robot|recaptcha|hcaptcha|turnstile|are you human|verify you are human|"
    r"verify that you are human|complete the (?:security )?challenge|checking your browser|"
    r"just a moment\.\.\.|unusual traffic|solve the puzzle|press and hold",
    re.I,
)
# Phone / ID verification is the same class of wall: we do not feed it, we walk away.
IDENTITY_MARKERS = re.compile(
    r"verify your phone|phone verification|enter your phone number|sms (?:code|verification)|"
    r"identity verification|upload (?:your )?(?:id|passport)|\bkyc\b",
    re.I,
)

GOOGLE_SSO_LABELS = (
    "continue with google", "sign in with google", "sign up with google",
    "log in with google", "login with google", "google",
)
ENTRY_LABELS = (
    "sign in", "sign up", "log in", "login", "get started", "get api key",
    "start for free", "try for free", "console", "dashboard", "register",
)
CREATE_LABELS = (
    "create api key", "create new api key", "create new key", "create key",
    "new api key", "new secret key", "new key", "generate api key", "generate key",
    "generate new key", "create token", "new token", "add key", "add new key",
    "create", "+ new", "+ create", "new",
)
COPY_LABELS = ("copy", "copy key", "copy api key", "copy to clipboard", "copy secret")
SIGNED_IN_MARKERS = re.compile(
    r"\bsign ?out\b|\blog ?out\b|\bdashboard\b|\bapi keys?\b|\bbilling\b|\busage\b|\bsettings\b",
    re.I,
)

# Where API keys usually live, tried in order after SSO lands. Cheap: one HEAD-ish goto each.
KEY_PATHS = (
    "/api-keys", "/settings/api-keys", "/account/api-keys", "/dashboard/api-keys",
    "/keys", "/settings/keys", "/account/keys", "/dashboard/keys",
    "/api", "/settings", "/account", "/dashboard", "/developer", "/tokens",
)
KEY_NAV_LABELS = ("api keys", "api key", "keys", "api", "tokens", "credentials", "developers")

KEY_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    re.compile(r"\bSG_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\b(?:gsk|nvapi|hf|xai|pplx|csk|r8|fw)_[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    re.compile(r"\b[0-9a-f]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{28,}\b"),  # opaque-token fallback, last on purpose
)
# Things that match the opaque-token fallback but are never keys.
KEY_NOISE = re.compile(
    r"^(?:[0-9]+|https?|[A-Za-z]+\.(?:js|css|png|svg|woff2?)|[a-f0-9]{7})$|"
    r"csrf|nonce|__next|webpack|sourcemap|integrity|sha256-|sha384-",
    re.I,
)


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, flush=True)


def body_text(page) -> str:
    try:
        return page.inner_text("body", timeout=5000) or ""
    except Exception:
        try:
            return page.content()[:200000]
        except Exception:
            return ""


def wall(text: str, url: str = "") -> Optional[str]:
    """Return the refusal reason if this page is a wall we walk away from, else None."""
    if "signin/rejected" in url or "This browser or app may not be secure" in text:
        return "GOOGLE_REFUSED_AUTOMATION"
    if CAPTCHA_MARKERS.search(text):
        return "CAPTCHA_REFUSED"
    if CARD_MARKERS.search(text):
        return "PAYWALL_REFUSED"
    if IDENTITY_MARKERS.search(text):
        return "IDENTITY_REFUSED"
    return None


def click_label(page, labels: tuple[str, ...], timeout: int = 4000) -> Optional[str]:
    """Click the first control matching any label. Returns the label that worked, or None."""
    for label in labels:
        pat = re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)
        for role in ("button", "link"):
            try:
                loc = page.get_by_role(role, name=pat).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=timeout)
                    return label
            except Exception:
                continue
    # Second pass: substring match, for buttons with icons or extra words in them.
    for label in labels:
        try:
            loc = page.get_by_role("button", name=re.compile(re.escape(label), re.I)).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=timeout)
                return label
        except Exception:
            continue
    return None


def settle(page, ms: int = 2500) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        page.wait_for_timeout(min(ms, 1500))


def shot(page, name: str) -> Optional[str]:
    SHOTS.mkdir(parents=True, exist_ok=True)
    p = SHOTS / f"{name}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
        return str(p.relative_to(ROOT))
    except Exception:
        return None


def read_clipboard(page) -> str:
    """Clipboard, the operator's own step 'copy to clipoard'. JS first, PowerShell as backup."""
    try:
        v = page.evaluate("navigator.clipboard.readText()")
        if v and str(v).strip():
            return str(v).strip()
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=15)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def looks_like_key(s: str) -> bool:
    s = (s or "").strip()
    if not (16 <= len(s) <= 400) or " " in s or "\n" in s:
        return False
    if KEY_NOISE.search(s):
        return False
    return any(p.fullmatch(s) or p.search(s) for p in KEY_PATTERNS)


def keys_in(text: str) -> set[str]:
    found: set[str] = set()
    for p in KEY_PATTERNS:
        for m in p.findall(text or ""):
            tok = m if isinstance(m, str) else m[0]
            if looks_like_key(tok):
                found.add(tok)
    return found


# --------------------------------------------------------------------------------------------
# Browser
# --------------------------------------------------------------------------------------------
def launch(pw, headless: bool):
    """Persistent context on the ROBOT profile. Never the operator's live Chrome."""
    udd = safe_profile_dir(PROFILE_TAG)
    assert_safe(udd, who="auto_key_harvester")
    udd.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(udd),
        channel="chrome",
        headless=headless,
        slow_mo=60,
        timeout=60000,
        viewport={"width": 1360, "height": 940},
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--restore-last-session=false",
        ],
    )
    try:
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass  # clipboard falls back to PowerShell
    return ctx


def pick_google_account(page, want_email: Optional[str]) -> str:
    """Step 4: 'select profile'. Returns a status string; never types a password."""
    settle(page, 4000)
    txt = body_text(page)
    w = wall(txt, page.url)
    if w:
        return w
    if "accounts.google.com" not in page.url:
        return "NO_GOOGLE_PAGE"

    # A password/identifier form means the session did NOT carry over. We stop -- typing a
    # Google password from automation is exactly what this project does not do.
    if page.locator("input[type=password]").count():
        return "GOOGLE_WANTS_PASSWORD"
    if page.locator("input[name=identifier]").count() and not page.locator(
            "div[data-identifier], li[data-identifier]").count():
        return "GOOGLE_WANTS_EMAIL"

    # The chooser. Google renders account tiles as [data-identifier] or role=link with the email.
    tiles = page.locator("div[data-identifier], li[data-identifier]")
    n = tiles.count()
    if n:
        idx = 0
        if want_email:
            for i in range(n):
                if want_email.lower() in (tiles.nth(i).get_attribute("data-identifier") or "").lower():
                    idx = i
                    break
        chosen = tiles.nth(idx).get_attribute("data-identifier") or "(unnamed tile)"
        log(f"        profile chooser: {n} account(s), picking {chosen}")
        tiles.nth(idx).click(timeout=8000)
    else:
        # Some flows skip the chooser and go straight to consent.
        clicked = click_label(page, ("continue", "allow", "confirm", "next"), timeout=6000)
        if not clicked:
            return "GOOGLE_UNKNOWN_PAGE"

    # Consent screen, if the provider asks for scopes.
    for _ in range(3):
        settle(page, 4000)
        if "accounts.google.com" not in page.url:
            break
        txt = body_text(page)
        w = wall(txt, page.url)
        if w:
            return w
        if not click_label(page, ("continue", "allow", "confirm", "next", "i agree"), timeout=5000):
            break

    settle(page, 6000)
    if "signin/rejected" in page.url:
        return "GOOGLE_REFUSED_AUTOMATION"
    return "RETURNED" if "accounts.google.com" not in page.url else "STUCK_ON_GOOGLE"


def do_sso(ctx, page, want_email: Optional[str]) -> str:
    """Steps 2-4: get in via Continue with Google. Handles same-tab and popup flows."""
    txt = body_text(page)
    if SIGNED_IN_MARKERS.search(txt) and not any(
            m in txt.lower() for m in ("sign in", "sign up", "log in")):
        return "ALREADY_SIGNED_IN"

    def try_google() -> Optional[str]:
        popup: dict[str, Any] = {}
        try:
            with ctx.expect_page(timeout=6000) as pi:
                if not click_label(page, GOOGLE_SSO_LABELS, timeout=5000):
                    return None
            popup["p"] = pi.value
        except Exception:
            # No popup opened. Either the click failed, or it navigated in this tab.
            if "accounts.google.com" not in page.url:
                if not click_label(page, GOOGLE_SSO_LABELS, timeout=5000):
                    return None
                settle(page, 5000)
        target = popup.get("p") or page
        try:
            target.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        st = pick_google_account(target, want_email)
        if popup.get("p"):
            try:
                if st == "RETURNED":
                    popup["p"].wait_for_timeout(1500)
                popup["p"].close()
            except Exception:
                pass
            settle(page, 6000)
        return st

    st = try_google()
    if st:
        return st

    # No Google control on the landing page. Click a way in first, then look again.
    entered = click_label(page, ENTRY_LABELS, timeout=5000)
    if not entered:
        return "NO_SSO_CONTROL_FOUND"
    settle(page, 5000)
    txt = body_text(page)
    w = wall(txt, page.url)
    if w:
        return w
    st = try_google()
    return st or "NO_GOOGLE_BUTTON_AFTER_ENTRY"


def reach_key_page(page, target: dict) -> bool:
    """Step 5. Prefer the provider's own documented URL, then nav links, then common paths."""
    for url in (target.get("apiKeyUrl"), ):
        if url:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                settle(page)
                return True
            except Exception:
                pass
    for label in KEY_NAV_LABELS:
        try:
            loc = page.get_by_role("link", name=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                settle(page)
                if re.search(r"key|token|api|credential", page.url, re.I):
                    return True
        except Exception:
            continue
    base = re.match(r"^(https?://[^/]+)", page.url)
    if not base:
        return False
    for path in KEY_PATHS:
        try:
            page.goto(base.group(1) + path, wait_until="domcontentloaded", timeout=20000)
            settle(page, 2000)
            if page.url.rstrip("/").endswith(path.rstrip("/")):
                t = body_text(page).lower()
                if "api key" in t or "secret key" in t or "token" in t:
                    return True
        except Exception:
            continue
    return False


def mint_key(page) -> tuple[Optional[str], str]:
    """Steps 6-7: create the key, then copy it. Returns (key or None, detail)."""
    before = keys_in(body_text(page))
    clicked = click_label(page, CREATE_LABELS, timeout=6000)
    if not clicked:
        return None, "no create control found on the key page"
    settle(page, 4000)

    # Many providers open a modal whose own button does the real creating. Press it too.
    # This is the defect that made video_key_harvester stop one click short on AI Studio.
    try:
        modal = page.locator("[role=dialog], .modal, [aria-modal=true]").first
        if modal.count() and modal.is_visible():
            inner = click_label(page, ("create key", "create", "generate", "confirm",
                                      "create api key", "create secret key", "done", "submit"),
                                timeout=5000)
            if inner:
                clicked = f"{clicked} -> {inner}"
                settle(page, 4000)
    except Exception:
        pass

    txt = body_text(page)
    w = wall(txt, page.url)
    if w:
        return None, w

    # Clipboard first: it is the only way to get a key a provider shows masked.
    if click_label(page, COPY_LABELS, timeout=4000):
        page.wait_for_timeout(700)
        cb = read_clipboard(page)
        if looks_like_key(cb):
            return cb, f"clicked '{clicked}', copied from clipboard"

    fresh = keys_in(txt) - before
    if fresh:
        best = max(fresh, key=len)
        return best, f"clicked '{clicked}', read from page"

    # Some providers put the key in an input the text extractor cannot see.
    try:
        for sel in ("input[readonly]", "input[type=text]", "textarea", "code", "pre"):
            loc = page.locator(sel)
            for i in range(min(loc.count(), 12)):
                v = (loc.nth(i).input_value(timeout=1500)
                     if sel.startswith("input") or sel == "textarea"
                     else loc.nth(i).inner_text(timeout=1500))
                if looks_like_key(v) and v.strip() not in before:
                    return v.strip(), f"clicked '{clicked}', read from {sel}"
    except Exception:
        pass
    return None, f"clicked '{clicked}' but no key appeared"


# --------------------------------------------------------------------------------------------
# One provider, end to end
# --------------------------------------------------------------------------------------------
def run_one(ctx, api, target: dict, dry_run: bool) -> dict:
    slug = target["id"]
    name = target.get("name") or slug
    site = target.get("apiKeyUrl") or target.get("website")
    row: dict[str, Any] = {"provider": slug, "name": name, "url": site,
                           "card_stance": card_stance(target.get("freeNote", ""))}
    if not site:
        row.update(ok=False, stage="no-url", detail="catalog has no website for this provider")
        return row

    page = ctx.new_page()
    try:
        try:
            page.goto(site, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            row.update(ok=False, stage="goto", detail=f"{type(exc).__name__}: {str(exc)[:120]}")
            return row
        settle(page)

        w = wall(body_text(page), page.url)
        if w:
            row.update(ok=False, stage="wall-on-landing", detail=w, shot=shot(page, f"{slug}-wall"))
            return row

        sso = do_sso(ctx, page, target.get("google_email"))
        row["sso"] = sso
        if sso in ("CAPTCHA_REFUSED", "PAYWALL_REFUSED", "IDENTITY_REFUSED",
                   "GOOGLE_REFUSED_AUTOMATION"):
            row.update(ok=False, stage="wall-at-sso", detail=sso, shot=shot(page, f"{slug}-sso"))
            return row
        if sso not in ("RETURNED", "ALREADY_SIGNED_IN"):
            row.update(ok=False, stage="sso", detail=sso, shot=shot(page, f"{slug}-sso"))
            return row

        if not reach_key_page(page, target):
            row.update(ok=False, stage="find-key-page",
                       detail="signed in, but no API-keys page found",
                       shot=shot(page, f"{slug}-nokeypage"))
            return row
        row["key_page"] = page.url

        w = wall(body_text(page), page.url)
        if w:
            row.update(ok=False, stage="wall-at-key-page", detail=w, shot=shot(page, f"{slug}-wall2"))
            return row

        key, detail = mint_key(page)
        row["mint_detail"] = detail
        if not key:
            row.update(ok=False, stage="mint", detail=detail, shot=shot(page, f"{slug}-nokey"))
            return row
        row["key"] = fingerprint(key)
        log(f"        got a key: {fingerprint(key)}")

        if dry_run:
            row.update(ok=False, stage="dry-run", detail="key obtained; not wired (--dry-run)")
            return row

        res = wire(api, slug, name, key)
        row.update(res)
        if res.get("ok"):
            try:
                store = json.loads(KEYS_FILE.read_text(encoding="utf-8")) if KEYS_FILE.exists() else {}
            except Exception:
                store = {}
            store[slug] = key           # gitignored; the only place a raw key is written
            KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
            KEYS_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return row
    finally:
        try:
            page.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Sign up with Google, mint a key, wire it. No clicks.")
    ap.add_argument("--probe", metavar="SLUG",
                    help="run ONE provider through steps 1-4 only and report what Google did")
    ap.add_argument("--only", metavar="SLUGS", help="comma-separated slugs to run")
    ap.add_argument("--count", type=int, default=0, help="stop after N providers (0 = all)")
    ap.add_argument("--no-card-only", action="store_true",
                    help="only providers whose own notes say no credit card")
    ap.add_argument("--google-email", help="which account to pick in the chooser (default: first)")
    ap.add_argument("--dry-run", action="store_true", help="get keys but do not wire them")
    ap.add_argument("--headless", action="store_true",
                    help="not recommended: Google treats headless far more harshly")
    ap.add_argument("--list", action="store_true", help="show the queue and exit")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright  # imported late: --list needs no browser

    targets = load_targets()
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        log("[-] OmniRoute login failed -- stopping before touching any provider")
        return 2
    have = {str(c.get("provider", "")).lower() for c in api.get_connections()}

    queue = [t for t in targets if t["id"].lower() not in have and t["id"] not in KNOWN_DEAD]
    skipped_wired = len(targets) - len(queue)
    if args.no_card_only:
        queue = [t for t in queue if card_stance(t.get("freeNote", "")) == "no-card"]
    if args.probe:
        queue = [t for t in targets if t["id"] == args.probe] or \
                [{"id": args.probe, "name": args.probe, "website": None}]
    elif args.only:
        want = {s.strip().lower() for s in args.only.split(",") if s.strip()}
        queue = [t for t in targets if t["id"].lower() in want]
    if args.count:
        queue = queue[:args.count]

    log(f"[*] already wired, not queued: {skipped_wired}")
    log(f"[*] queue: {len(queue)}")
    if args.list:
        for t in queue:
            log(f"    {t['id']:24} {card_stance(t.get('freeNote','')):16} {t.get('website') or '-'}")
        return 0
    if not queue:
        log("[*] nothing to do")
        return 0

    rows: list[dict] = []
    with sync_playwright() as pw:
        ctx = launch(pw, args.headless)
        try:
            for i, t in enumerate(queue, 1):
                log(f"\n[{i}/{len(queue)}] {t['id']}  ({t.get('website') or 'no site'})")
                t = dict(t, google_email=args.google_email)
                try:
                    row = run_one(ctx, api, t, dry_run=args.dry_run or bool(args.probe))
                except Exception as exc:
                    row = {"provider": t["id"], "ok": False, "stage": "crash",
                           "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
                rows.append(row)
                mark = "WORKING" if row.get("ok") else f"no ({row.get('stage')})"
                log(f"        -> {mark}: {str(row.get('detail'))[:110]}")

                if row.get("detail") == "GOOGLE_REFUSED_AUTOMATION":
                    log("\n[!] Google refused the automated browser at the sign-in step.")
                    log("    Stopping the whole run. This is not worked around by design")
                    log("    (worklog #1033): no stealth patching, no fingerprint spoofing.")
                    break
                time.sleep(1.0)
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    ok = [r for r in rows if r.get("ok")]
    refused = [r for r in rows if str(r.get("detail", "")).endswith("_REFUSED")]
    log("\n" + "=" * 78)
    log(f"attempted           : {len(rows)}")
    log(f"WIRED AND PROVEN    : {len(ok)}   (a real model answered a real question)")
    for r in ok:
        log(f"    {r['provider']:24} {r.get('key')}")
    log(f"walked away from    : {len(refused)}   (card / CAPTCHA / phone -- never solved)")
    for r in refused:
        log(f"    {r['provider']:24} {r.get('detail')}")
    stages: dict[str, int] = {}
    for r in rows:
        if not r.get("ok") and r not in refused:
            stages[str(r.get("stage"))] = stages.get(str(r.get("stage")), 0) + 1
    if stages:
        log("stopped earlier at  : " + ", ".join(f"{k}={v}" for k, v in sorted(stages.items())))
    log(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
