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
    find_chrome,
    fingerprint,
    load_targets,
    real_completion,
    wire,
)
from provider_login_helper import ROBOT_CDP_PORT  # noqa: E402

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
# The site refusing to serve us at all. MEASURED on blackbox 2026-08-22: blackbox.ai served a
# bare "Error: Forbidden / 403: Forbidden" page, and the run spent its whole budget hunting for a
# Google button that could never be there. A blocked page is an answer; name it and move on.
# Guarded by body length in wall_page(): a real block page is tiny, while a dashboard that merely
# mentions "403" somewhere in its docs text is not blocked.
BLOCKED_MARKERS = re.compile(
    r"error: forbidden|403[^0-9]{0,3}forbidden|access denied|request blocked", re.I)

GOOGLE_SSO_LABELS = (
    "continue with google", "sign in with google", "sign up with google",
    "log in with google", "login with google", "google",
)
ENTRY_LABELS = (
    "sign in", "sign up", "log in", "login", "get started", "get api key",
    "start for free", "try for free", "console", "dashboard", "register",
)
# Cookie/consent overlays. MEASURED on sambanova 2026-08-22: a TrustArc banner ("We Value Your
# Privacy" / "Agree & Proceed") covered the viewport, so every later click either hit the banner
# or was refused as intercepted. Dismissing these is not optional -- it is step zero.
COOKIE_LABELS = (
    "agree & proceed", "agree and proceed", "accept all cookies", "accept all", "allow all",
    "accept cookies", "accept", "i agree", "agree", "got it", "ok, got it", "understood",
    "continue", "close", "dismiss", "reject all",  # reject-all is fine: we want it gone, not set
)
# The catalog's `website` is a MARKETING homepage for most providers, not the signup console.
# MEASURED on sambanova: https://sambanova.ai has no login at all; the console is
# cloud.sambanova.ai. Navigation therefore follows EVIDENCE ONLY -- the provider's documented
# URLs, the URLs named in its own catalog notes, and the anchors the page itself renders.
# Conventional-subdomain fabrication (app./cloud./console.) and stock-path probing were REMOVED
# 2026-08-22 on the operator's call: trying many invented URLs is the wrong way to find the
# correct path, it burns the per-provider budget, and hammering 100+ provider domains with
# guess-request after guess-request is exactly how an IP ends up blacklisted by their WAFs.
AUTH_HREF_RE = re.compile(
    r"(?:^|[./_-])(?:log[-_]?in|sign[-_]?in|sign[-_]?up|signup|register|console|cloud|"
    r"platform|dashboard|developer|studio|workbench)(?:[./?#_-]|$)", re.I)
# Anchor TEXT patterns for DOM-study navigation. A visible control that says "Sign in" is the
# page telling us where the door is; that outranks any URL shape.
ENTRY_TEXT_RE = re.compile(
    r"sign ?in|sign ?up|log ?in|login|register|get started|console|dashboard|launch app", re.I)
KEY_NAV_TEXT_RE = re.compile(r"api ?keys?|tokens?|credentials|developers?", re.I)
KEY_PATH_RE = re.compile(r"/(?:api-?)?keys?|/tokens?|/credentials|/developers?", re.I)
CREATE_LABELS = (
    "create api key", "create new api key", "create new key", "create key",
    "new api key", "new secret key", "new key", "generate api key", "generate key",
    "generate new key", "create token", "new token", "add key", "add new key",
    "create", "+ new", "+ create", "new",
)
COPY_LABELS = ("copy", "copy key", "copy api key", "copy to clipboard", "copy secret")
# ONLY a sign-out control proves a session exists. MEASURED on cloud.sambanova.ai/plans/pricing
# 2026-08-22: that page is PUBLIC, and its shell nav carries Dashboard / Billing / Settings /
# "API keys", so the earlier, broader marker set reported ALREADY_SIGNED_IN while logged out.
# Everything except an explicit sign-out link is furniture that public pages also render.
SIGNED_IN_MARKERS = re.compile(r"\bsign ?out\b|\blog ?out\b|\blogout\b|\bmy account\b", re.I)

# Where API keys usually live -- NO LONGER probed as stock paths. Kept only as the URL-shape
# half of DOM-study scoring: an anchor whose href matches this AND whose text says "API keys"
# is evidence; an href alone, sprayed at the site, is a guess.

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

# Parked by the operator mid-run, 2026-08-22: "lets park this provider and move on wasting our
# time" / "we have 100s yet to cover". NOT a dead end -- sambanova is where the Google chooser
# first proved it works under Playwright. It is parked because per-provider debugging does not
# scale when 100+ providers have never been tried once. Revisit after the sweep.
PARKED = {
    "sambanova": "operator parked 2026-08-22 after its chooser proved the Google flow works; "
                 "breadth first, single-provider polish later",
}


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, flush=True)


# A hard per-provider time budget. Without it one slow site eats the sweep, which is exactly the
# failure the operator called out: "we have 100s yet to cover". Breadth beats depth here.
_deadline: float = 0.0
# Current provider slug, so deep helpers (chooser handling) can name their screenshots without
# threading a parameter through five call layers.
_shot_prefix: str = "page"


def out_of_time() -> bool:
    return _deadline > 0 and time.monotonic() > _deadline


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
    # Second pass: substring match, for controls with icons or extra words in their names.
    # Links are included too -- MEASURED on featherless.ai 2026-08-22: the real door was a
    # 'Login' anchor whose accessible name had extra text, the exact pass missed it, and the
    # next label in line ('get started') walked the run into the model playground instead.
    for label in labels:
        pat = re.compile(re.escape(label), re.I)
        for role in ("button", "link"):
            try:
                loc = page.get_by_role(role, name=pat).first
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


# --------------------------------------------------------------------------------------------
# DOM study -- navigation is guided by the DOM the page actually has, not by guessing labels.
# Anti-pattern #11 (Visual & DOM Diagnosis Protocol): screenshot first, study the DOM second,
# act third, screenshot after. Everything below feeds both the acting and the diagnosis trail.
# --------------------------------------------------------------------------------------------
DOM_STUDY_JS = """() => {
    const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const anchors = [...document.querySelectorAll('a[href]')].filter(vis).slice(0, 120)
        .map(a => ({t: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 60),
                    h: a.href}));
    const buttons = [...document.querySelectorAll('button, [role=button], input[type=submit]')]
        .filter(vis).slice(0, 80)
        .map(b => ({t: (b.innerText || b.getAttribute('aria-label') || b.value || '')
                    .trim().slice(0, 60)}));
    const forms = [...document.querySelectorAll('form')].slice(0, 10).map(f => f.action);
    const inputs = [...document.querySelectorAll('input')].slice(0, 30).map(i => i.type);
    const iframes = [...document.querySelectorAll('iframe')].map(f => f.src).slice(0, 10);
    return {url: location.href, title: document.title, anchors, buttons, forms, inputs, iframes};
}"""


def dom_study(page) -> dict:
    """One structured look at the page's interactive surface: visible anchors with hrefs,
    buttons with names, forms, input types, iframes. Returns {} if the DOM will not talk.

    This is what GUIDES NAVIGATION: candidate login links are scored from these anchors, and
    when a step fails the button inventory goes into the report, so the next agent can see what
    the page offered instead of re-guessing.
    """
    try:
        return page.evaluate(DOM_STUDY_JS) or {}
    except Exception:
        return {}


def dom_button_names(dom: dict) -> list[str]:
    return [b.get("t", "") for b in dom.get("buttons", []) if b.get("t")]


CARD_INPUT_SEL = (
    "input[name*=card i], input[id*=card i], input[placeholder*=card i], "
    "input[autocomplete*='cc-' i], input[name*=cvc i], input[name*=cvv i], "
    "input[id*=cvc i], input[id*=cvv i], input[name*=expir i], input[id*=expir i], "
    "input[placeholder*=expir i], input[name*=cardholder i], input[id*=cardholder i]"
)


# CAPTCHA by DOM shape, not just text. MEASURED on openadapter 2026-08-22 (operator: 'captcha
# wall'): dashboard.openadapter.in threw a Cloudflare challenge whose page text is EMPTY -- the
# widget renders inside an iframe from challenges.cloudflare.com, so every text marker missed
# it and the run sat on the challenge instead of walking away. These selectors see what the
# operator sees.
CAPTCHA_DOM_SEL = (
    "iframe[src*='challenges.cloudflare.com']", "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']", ".cf-turnstile", "[data-sitekey]", ".g-recaptcha",
    ".h-captcha", "#challenge-running", "[class*='cf-chl']",
)


def captcha_dom_present(page) -> bool:
    for fr in frames_of(page):
        for sel in CAPTCHA_DOM_SEL:
            try:
                if fr.locator(sel).count():
                    return True
            except Exception:
                continue
    return False


def card_form_present(page) -> bool:
    """Is there an actual card FORM in the DOM (any frame, Stripe iframes included)?

    MEASURED on inception 2026-08-22: docs.inceptionlabs.ai's landing page was refused as
    PAYWALL_REFUSED because its marketing copy matched CARD_MARKERS ('start your free trial'
    in a navbar) -- while the screenshot shows no card form anywhere on the page. Marketing
    words are not a paywall; an input that wants card digits is.
    """
    for fr in frames_of(page):
        try:
            if fr.locator(CARD_INPUT_SEL).count():
                return True
        except Exception:
            continue
    return False


def wall_page(page) -> Optional[str]:
    """wall() for a live page: text markers backed by DOM evidence where DOM evidence exists.

    Differences from wall(), both measured 2026-08-22:
    * PAYWALL_REFUSED additionally requires card_form_present() -- see that docstring.
    * SITE_REFUSED recognises a tiny blocked page (403 Forbidden) instead of hunting a Google
      button on an error page that will never have one (blackbox).
    """
    txt = body_text(page)
    if "signin/rejected" in page.url or "This browser or app may not be secure" in txt:
        return "GOOGLE_REFUSED_AUTOMATION"
    if len(txt) < 1200 and BLOCKED_MARKERS.search(txt):
        return "SITE_REFUSED"
    # A DOM-detected challenge widget counts as a wall only when the page offers NOTHING else:
    # full-page interstitials (openadapter's Turnstile) have near-empty text. Ordinary login
    # pages often embed an invisible reCAPTCHA next to a perfectly usable form -- those are NOT
    # walls, and refusing them would nuke the whole sweep.
    if CAPTCHA_MARKERS.search(txt) or (captcha_dom_present(page) and len(txt) < 600):
        return "CAPTCHA_REFUSED"
    if CARD_MARKERS.search(txt) and card_form_present(page):
        return "PAYWALL_REFUSED"
    if IDENTITY_MARKERS.search(txt):
        return "IDENTITY_REFUSED"
    return None


# Icon-only account doors. MEASURED on featherless.ai 2026-08-22: the landing page's ONLY
# login control is a circular user avatar with no text anywhere -- label clicks and text-ranked
# DOM links all miss it. These press account-shaped icon controls; the follow-up poll decides
# whether the press actually opened a door.
ICON_LOGIN_SEL = (
    "[aria-label*='sign in' i]", "[aria-label*='log in' i]", "[aria-label*='login' i]",
    "[aria-label*='account' i]", "[aria-label*='user' i]", "[aria-label*='profile' i]",
    "a:has(i[class*='user' i])", "button:has(i[class*='user' i])",
)


def icon_login_click(page) -> bool:
    for sel in ICON_LOGIN_SEL:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def wait_for_control(page, labels: tuple[str, ...], roles: tuple[str, ...] = ("button", "link"),
                     ms: int = 15000) -> Optional[str]:
    """Poll until one of these labels exists as a visible control, then click it.

    The Auth0 lesson (wait_for_auth_ui) applies to key pages too. MEASURED on featherless.ai
    2026-08-22: mint_key ran the instant reach_key_page returned, the 'New API Key' button had
    not rendered yet, click_label found nothing, and the run reported 'no create control found'
    about a page whose screenshot shows the button plain as day. The control appearing is the
    signal; domcontentloaded is not.
    """
    end = time.monotonic() + ms
    while True:
        for label in labels:
            pat = re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)
            for role in roles:
                try:
                    loc = page.get_by_role(role, name=pat).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=4000)
                        return label
                except Exception:
                    continue
        if time.monotonic() >= end or out_of_time():
            return None
        page.wait_for_timeout(1000)


def dismiss_overlays(page) -> list[str]:
    """Step zero: clear cookie/consent banners so later clicks reach the real controls.

    Runs after every navigation. Only ever presses the banner's own dismiss control -- it does
    not hunt for hidden elements or rip nodes out of the DOM.
    """
    gone: list[str] = []
    for _ in range(3):
        hit = None
        for sel in ("#truste-consent-track", "[id*=cookie i]", "[class*=cookie i]",
                    "[id*=consent i]", "[class*=consent i]", "[aria-label*=cookie i]",
                    "[role=dialog]", ".cc-window", "#onetrust-banner-sdk"):
            try:
                box = page.locator(sel).first
                if not (box.count() and box.is_visible()):
                    continue
                for label in COOKIE_LABELS:
                    btn = box.get_by_role("button", name=re.compile(re.escape(label), re.I)).first
                    if btn.count() and btn.is_visible():
                        btn.click(timeout=3000)
                        hit = f"{sel}:{label}"
                        break
                if not hit:
                    x = box.locator("button[aria-label*=close i], button[aria-label*=dismiss i]").first
                    if x.count() and x.is_visible():
                        x.click(timeout=3000)
                        hit = f"{sel}:close"
                if hit:
                    break
            except Exception:
                continue
        if not hit:
            break
        gone.append(hit)
        page.wait_for_timeout(500)
    return gone


def is_api_endpoint(url: str) -> bool:
    """True for raw inference/API endpoints (api.openadapter.in/v1, inference-api.nousresearch.com).
    The catalog's authHint documents the provider's API base for WIRING purposes; opening it in
    a browser just renders raw JSON (operator: 'why hitting this url', 2026-08-22). Login pages
    never live there, so note-guided navigation must skip them."""
    host = host_of(url)
    m = re.match(r"^https?://[^/]+(/.*)?$", url or "")
    path = (m.group(1) if m else "") or "/"
    return bool(
        host and (
            host.startswith("api.") or host.startswith("api-")
            or host.startswith("inference-api.") or host.startswith("inference.")
            or bool(re.match(r"^/v\d+($|/)", path))
        )
    )


def note_urls(target: dict) -> list[str]:
    """URLs the provider's own catalog note points at, EXCLUDING raw API endpoints.

    MEASURED on openadapter 2026-08-22: the marketing site openadapter.dev has no login, but its
    freeNote literally says 'Get your API key at https://dashboard.openadapter.in' -- a different
    registrable domain, so same-domain link scraping could never find it. The provider's own
    words are the best navigation hint there is; mine them. But authHint ALSO names the API base
    (https://api.openadapter.in/v1) -- that one is for wiring, not for visiting.
    """
    out: list[str] = []
    for field in ("freeNote", "authHint"):
        for m in re.finditer(r"https?://[^\s'\"<>)\]]+", str(target.get(field) or "")):
            u = m.group(0).rstrip(".,;")
            if not is_api_endpoint(u):
                out.append(u)
    return out


def host_of(url: str) -> str:
    m = re.match(r"^https?://([^/?#]+)", url or "")
    if m:
        return re.sub(r"^www\.", "", m.group(1)).lower()
    # Bare hostname (no scheme): same_site() and the wrong-console guard pass hosts, not just
    # URLs. MEASURED on the first e2e sweep: the guard refused inception's own console because
    # host_of('platform.inceptionlabs.ai') returned '' and same_site therefore never matched.
    if re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", (url or "").strip()):
        return re.sub(r"^www\.", "", (url or "").strip()).lower()
    return ""


def same_site(a: str, b: str) -> bool:
    a, b = host_of(a), host_of(b)
    return bool(a and b) and a.split(".")[-2:] == b.split(".")[-2:]


def dom_nav_links(page, kind: str) -> list[dict]:
    """DOM study: the page's own visible anchors that lead to auth ('auth') or key ('keys') pages.

    Each hit is evidence the page itself rendered -- ranked by how explicit it is (the anchor's
    visible text outranks the shape of its href). This is what guides navigation; nothing is
    invented here. Cross-domain links are followed only when the anchor's own text names the
    destination (e.g. a marketing site linking its console on another domain); an href shape
    alone is not enough to leave the provider's site.
    """
    dom = dom_study(page)
    page_host = host_of(dom.get("url") or page.url)
    out: list[dict] = []
    seen: set[str] = set()
    for a in dom.get("anchors", []):
        text = str(a.get("t") or "").strip()
        href = str(a.get("h") or "").strip()
        if not href or href.lower() in seen:
            continue
        text_hit = bool(ENTRY_TEXT_RE.search(text)) if kind == "auth" \
            else bool(KEY_NAV_TEXT_RE.search(text))
        href_hit = bool(AUTH_HREF_RE.search(href.split("//", 1)[-1])) if kind == "auth" \
            else bool(KEY_PATH_RE.search(href))
        if not (text_hit or href_hit):
            continue
        if not same_site(href, page_host) and not text_hit:
            continue
        seen.add(href.lower())
        out.append({"text": text[:40] or "(icon link)", "href": href,
                    "score": (4 if text_hit else 0) + (2 if href_hit else 0)})
    out.sort(key=lambda x: -x["score"])
    return out[:6]


def _sibling_pages(page) -> list:
    try:
        return [p for p in page.context.pages if not p.is_closed()]
    except Exception:
        return [page]


def nav_click(page, href: str):
    """Click the page's own anchor for this href and FOLLOW where it went.

    Navigation is CLICK-BASED (operator, 2026-08-22): press the link the page renders -- no
    address-bar reloads. Clicking carries referrer and session context; a cold goto() at deep
    URLs is both unnatural and exactly the traffic pattern WAFs blacklist.

    Returns the page holding the destination: the SAME page for ordinary links, or the NEW TAB
    for target=_blank links. MEASURED on docs.inceptionlabs.ai 2026-08-22: every console link
    opens a new tab, and the old code kept probing the docs tab while the console sat unopened
    in another tab. None when the click failed or went nowhere.
    """
    try:
        loc = page.locator(f"a[href={json.dumps(href)}]").first
        if not (loc.count() and loc.is_visible()):
            return None
        before_pages = {id(p) for p in _sibling_pages(page)}
        url_before = page.url or ""
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        loc.click(timeout=5000)
    except Exception:
        return None
    follow = None
    end = time.monotonic() + 8
    while time.monotonic() < end:
        fresh = [p for p in _sibling_pages(page)
                 if id(p) not in before_pages and (p.url or "") not in ("", "about:blank")]
        if fresh:
            follow = fresh[-1]
            break
        if (page.url or "").rstrip("/") != url_before.rstrip("/"):
            break
        page.wait_for_timeout(500)
    tgt = follow or page
    try:
        tgt.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    settle(tgt, 3000)
    if follow is None and (page.url or "").rstrip("/") == url_before.rstrip("/"):
        return None   # the click went nowhere
    return tgt


def step_back(page) -> None:
    """After a candidate link led nowhere interesting, go back so the next candidate is still
    clickable. The candidates were read from the page we are going back to."""
    try:
        page.go_back(timeout=8000)
        settle(page, 2000)
    except Exception:
        pass


def adopt_popup(ctx, page, preexisting: frozenset = frozenset()):
    """A click that opened a new tab is still click-based navigation: follow the trail into it.

    `preexisting` is the set of page ids that existed before this provider's run started. Only
    pages born DURING the run may be adopted. MEASURED 2026-08-22: run 12 was cancelled
    mid-provider and left an orphan console tab open; run 13's featherless-ai then adopted that
    INCEPTION tab and nearly minted the wrong provider's key under the featherless name.
    """
    try:
        pages = [p for p in ctx.pages if not p.is_closed()]
    except Exception:
        return page
    if len(pages) <= 1:
        return page
    for p in reversed(pages):
        try:
            if p is not page and id(p) not in preexisting \
                    and p.url not in ("about:blank", "", page.url):
                return p
        except Exception:
            continue
    return page


def frames_of(page) -> list:
    """The page plus any child frames. Some providers render the login card in an iframe."""
    out = [page]
    try:
        out += [f for f in page.frames if f is not page.main_frame]
    except Exception:
        pass
    return out


def find_google_control(page):
    """The actual clickable 'Continue with Google', searched across frames. None if absent.

    Two detection layers, because role-name matching alone misses icon-only buttons:
    * accessible-name match against GOOGLE_SSO_LABELS;
    * DOM-shape match (DOM study): aria-labels mentioning google, buttons/links wrapping an
      img[alt*=google] -- the standard rendered 'G' logo button many SPAs ship unlabeled.
    """
    for fr in frames_of(page):
        for label in GOOGLE_SSO_LABELS:
            pat = re.compile(re.escape(label), re.I)
            for role in ("button", "link"):
                try:
                    loc = fr.get_by_role(role, name=pat).first
                    if loc.count() and loc.is_visible():
                        return loc
                except Exception:
                    continue
        for sel in ("[aria-label*='google' i]", "button:has(img[alt*='google' i])",
                    "a:has(img[alt*='google' i])", "[data-provider*='google' i]"):
            try:
                loc = fr.locator(sel).first
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                continue
    return None


def has_google_control(page) -> bool:
    return find_google_control(page) is not None


def wait_for_auth_ui(page, ms: int = 14000) -> str:
    """Poll until the page has decided what it is: a login card, or an authenticated page.

    MEASURED on cloud.sambanova.ai 2026-08-22: the Auth0 login card -- with 'Continue with
    Google' plainly on it -- had not painted yet when a 3s settle() expired, so the run reported
    NO_SSO_CONTROL_FOUND about a page that visibly HAD the control. domcontentloaded is not a
    useful signal for these SPA logins; the control appearing is.

    MEASURED on platform.inceptionlabs.ai 2026-08-22: the password field paints BEFORE the
    'Continue with Google' button on the same card, so returning "password" on first sight gave
    up early. The password field is now what we SETTLE for when the deadline expires, not a
    reason to stop looking for the Google button.
    """
    deadline = ms
    saw_password = False
    while deadline > 0:
        # NOTE: no out_of_time() here, on purpose. The budget bounds the hunt ACROSS candidate
        # pages (the loops that call this); it must not blind the poll on the page we are
        # already standing on -- MEASURED on inception/featherless 2026-08-22: reach_key_page
        # legitimately spends most of the budget navigating, and a deadline-checked poll then
        # returned instantly about a page that had the Google button ready.
        if find_google_control(page) is not None:
            return "google"
        try:
            if page.locator("input[type=password]").count():
                saw_password = True
        except Exception:
            pass
        txt = body_text(page)
        if wall_page(page):
            return "wall"
        if SIGNED_IN_MARKERS.search(txt):
            return "signed_in"
        page.wait_for_timeout(1000)
        deadline -= 1000
    return "password" if saw_password else "unknown"


# A login wall is decisive. If any of these hold, the page is NOT an authenticated page, no
# matter how much dashboard-looking furniture the SPA shell is still rendering around it.
LOGIN_WALL_URL_RE = re.compile(
    r"/login|/signin|/sign-in|/sign_in|/signup|/sign-up|/register|/auth(?:/|$|\?)|"
    r"auth0\.com|/u/login|okta\.com|/oauth", re.I)
LOGIN_WALL_TEXT_RE = re.compile(
    r"log ?in to |sign ?in to |don'?t have an account|already have an account\?|"
    r"forgot (?:your )?password|continue with (?:google|microsoft|github|apple)|"
    r"create your account|email address\*", re.I)


# SSO callback pages are TRANSIT, not walls. MEASURED on openadapter 2026-08-22: after Google
# consent the run landed on accounts.openadapter.in/sign-in/sso-callback?...redirect_url=... --
# which LOGIN_WALL_URL_RE happily matched ('sign-in') while the page was mid-redirect back to
# the dashboard, so a completed login reported 'still behind a login wall after SSO'.
CALLBACK_URL_RE = re.compile(r"sso-?callback|oauth-?callback|/auth/callback|/signin/callback", re.I)


def await_callback(page, ms: int = 15000) -> None:
    """Give an SSO callback page the time to finish walking us back to the provider."""
    end = time.monotonic() + ms
    while time.monotonic() < end:
        if not CALLBACK_URL_RE.search(page.url or ""):
            return
        page.wait_for_timeout(1000)
    settle(page, 3000)


def await_login_bounce(page, ms: int = 10000) -> None:
    """Post-SSO, a provider's /auth/login often bounces to the real destination a beat later
    (next-auth client-side redirect). MEASURED on inception 2026-08-22: the Google session was
    VALID -- /dashboard/api-keys loaded signed-in on a direct visit -- but the run judged the
    half-second-old /auth/login URL and reported 'still behind a login wall'. Give the bounce
    time before judging; stop early if a real password form shows up (that IS a wall)."""
    end = time.monotonic() + ms
    while time.monotonic() < end:
        try:
            if page.locator("input[type=password]").count():
                return
        except Exception:
            return
        if not login_wall(page):
            return
        page.wait_for_timeout(1000)


def login_wall(page) -> bool:
    try:
        if page.locator("input[type=password]").count():
            return True
    except Exception:
        pass
    if CALLBACK_URL_RE.search(page.url or ""):
        return False   # transit page -- see CALLBACK_URL_RE
    if LOGIN_WALL_URL_RE.search(page.url or ""):
        return True
    return bool(LOGIN_WALL_TEXT_RE.search(body_text(page)))


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


def attach(pw):
    """Attach to the ROBOT Chrome the OPERATOR started (HarvestChrome.cmd), instead of
    launching our own.

    WHY -- the operator's CAPTCHA concern, 2026-08-22: a Playwright-launched Chrome carries
    automation switches (navigator.webdriver=true) and provider WAFs score it as a bot
    (Turnstile on openadapter, measured). A Chrome started by a human on the same robot
    profile is an ordinary browser -- webdriver false, warm profile -- and the harvester just
    connects over the profile's own debugging port.

    SAFETY -- this is NOT the forbidden attach: chrome_live_guard refuses connect_over_cdp to
    any port advertised inside the operator's live Chrome tree; ROBOT_CDP_PORT belongs to
    state/automation_profiles/providers only. The operator's four profiles are not read,
    opened, or copied, ever.
    """
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}", timeout=10000)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    try:
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass
    return ctx


def restart_attached(pw, wait_s: int = 25):
    """The operator closed the harvest Chrome (or it died): start it again ourselves -- the
    SAME command line HarvestChrome.cmd uses, robot profile + guard -- and re-attach."""
    udd = safe_profile_dir(PROFILE_TAG)
    assert_safe(udd, who="auto_key_harvester.attach")
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("no installed chrome.exe found")
    subprocess.Popen(
        [str(chrome), f"--user-data-dir={udd}", f"--remote-debugging-port={ROBOT_CDP_PORT}",
         "--no-first-run", "--no-default-browser-check",
         "--window-size=1360,940", "--window-position=60,40", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        time.sleep(2)
        try:
            return attach(pw)
        except Exception:
            continue
    raise RuntimeError(f"robot Chrome did not come up on port {ROBOT_CDP_PORT} within {wait_s}s")


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
        shot(page, f"{_shot_prefix}-chooser")   # proof of step 4 before the click (anti-pattern 11)
        tiles.nth(idx).click(timeout=8000)
    else:
        # Some flows skip the chooser and go straight to consent.
        clicked = click_label(page, ("continue", "allow", "confirm", "next"), timeout=6000)
        if not clicked:
            return "GOOGLE_UNKNOWN_PAGE"

    # Consent screen, then the hand-off back to the provider. MEASURED on sambanova 2026-08-22:
    # the chooser worked and the account was clicked, but a fixed 6s settle expired while Google
    # was still bouncing through its redirect chain, so a working flow reported STUCK_ON_GOOGLE.
    # Poll instead of guessing a duration.
    waited = 0
    while waited < 30000:
        if "accounts.google.com" not in page.url:
            return "RETURNED"
        if "signin/rejected" in page.url:
            return "GOOGLE_REFUSED_AUTOMATION"
        txt = body_text(page)
        w = wall(txt, page.url)
        if w:
            return w
        click_label(page, ("continue", "allow", "confirm", "next", "i agree"), timeout=2500)
        page.wait_for_timeout(1500)
        waited += 1500
    return "STUCK_ON_GOOGLE"


def looks_signed_in(page) -> bool:
    """True only when there is no login wall AND the page shows account-only furniture.

    MEASURED on sambanova 2026-08-22: the first version of this returned True for an Auth0
    login card that had "Continue with Google" printed on it, because the SPA shell still
    carried nav words like Dashboard/Billing. That is the same false positive as
    provider_login_helper._classify() produces for kie. So the rule is now one-directional:
    ANY evidence of a login wall wins over ALL evidence of being signed in. Reporting "signed
    in" while looking at a login form is the exact dishonesty this project keeps banning.
    """
    if login_wall(page) or has_google_control(page):
        return False
    txt = body_text(page)
    if not SIGNED_IN_MARKERS.search(txt):
        return False
    low = txt.lower()
    return not any(m in low for m in ("sign in", "sign up", "log in", "create an account"))


def do_sso(ctx, page, target: dict, want_email: Optional[str]) -> str:
    """Steps 2-4: get in via Continue with Google. Handles same-tab, popup and new-tab flows.

    Hunts for the page that actually HAS the Google button instead of assuming the catalog's
    website is it. MEASURED on sambanova: the marketing homepage has no login anywhere, so the
    old 'click an entry label on the landing page' approach clicked a nav item and gave up.
    Every helper takes the page it works on, because a click may move the action to a NEW TAB
    (docs.inceptionlabs.ai measurement) and the flow must follow it there.
    """
    def click_google(p) -> bool:
        loc = find_google_control(p)
        if loc is None:
            return False
        try:
            loc.click(timeout=6000)
            return True
        except Exception:
            return False

    def try_google(p) -> Optional[str]:
        popup: dict[str, Any] = {}
        try:
            with ctx.expect_page(timeout=6000) as pi:
                if not click_google(p):
                    return None
            popup["p"] = pi.value
        except Exception:
            # No popup opened. Either the click failed, or it navigated in this tab.
            if "accounts.google.com" not in p.url:
                if not click_google(p):
                    return None
                settle(p, 5000)
        tgt = popup.get("p") or p
        try:
            tgt.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        st = pick_google_account(tgt, want_email)
        if st == "RETURNED":
            await_callback(tgt)   # the provider's sso-callback transit (openadapter lesson)
        if popup.get("p"):
            try:
                popup["p"].close()
            except Exception:
                pass
            settle(p, 6000)
            await_callback(p)
        return st

    def attempt_here(p) -> Optional[str]:
        """Try this page: Google button? Already in? A door to click, then a Google button?

        The Google check runs FIRST on purpose. A visible "Continue with Google" is the single
        most reliable fact on any of these pages -- more reliable than nav text, more reliable
        than the URL -- so it decides before anything else gets a vote.
        """
        dismiss_overlays(p)
        seen = wait_for_auth_ui(p)
        w = wall_page(p)
        if w:
            return w
        if seen == "google" or has_google_control(p):
            return try_google(p)
        if looks_signed_in(p):
            return "ALREADY_SIGNED_IN"
        if click_label(p, ENTRY_LABELS, timeout=4000) or icon_login_click(p):
            settle(p, 5000)
            dismiss_overlays(p)
            # Do not discard the poll: the password field paints before the Google button on
            # the same card (inception measurement above), so keep polling and use the result.
            seen = wait_for_auth_ui(p)
            w = wall_page(p)
            if w:
                return w
            if seen == "google" or has_google_control(p):
                return try_google(p)
            if looks_signed_in(p):
                return "ALREADY_SIGNED_IN"
        return None

    start_url = page.url
    st = attempt_here(page)
    if st:
        return st

    # An entry click may have dragged us off the landing page (MEASURED on featherless: 'Get
    # Started' opened the model playground). The candidates below were ranked from the landing
    # page; go back to it so they are actually clickable.
    if (page.url or "") != start_url:
        step_back(page)

    # Click-based hunt: press the landing page's own login links, best first, going back
    # between candidates. No URL reloads -- see nav_click for why.
    for link in dom_nav_links(page, "auth"):
        if out_of_time():
            return "OUT_OF_TIME"
        if link["href"].rstrip("/") == (page.url or "").rstrip("/"):
            continue
        follow = nav_click(page, link["href"])
        if follow is None:
            continue
        log(f"        clicking '{link['text']}' -> {follow.url}")
        st = attempt_here(follow)
        if st:
            return st
        if follow is not page:
            try:
                follow.close()
            except Exception:
                pass
        else:
            step_back(page)

    # Last resort: the provider's own documented entry points -- the catalog's apiKeyUrl and
    # the URLs in the provider's notes. Never guesses. One open each, logged as such.
    for url in [target.get("apiKeyUrl"), *note_urls(target)]:
        if out_of_time():
            return "OUT_OF_TIME"
        url = (url or "").split("#")[0].rstrip("/")
        if not url or url == (page.url or "").rstrip("/"):
            continue
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            continue
        settle(page, 3000)
        log(f"        documented entry point: {url}")
        st = attempt_here(page)
        if st:
            return st
    return "NO_SSO_CONTROL_FOUND"


def looks_like_key_page(page) -> bool:
    """Honest classification of the current page as a key-management page.

    The sambanova lesson applies here too: public pages happily say "API keys" in their nav. So
    either the URL we actually landed on is key-shaped, or the page says key words AND carries
    signed-in-only furniture (looks_signed_in). A login wall in front disqualifies both.
    """
    if login_wall(page) or has_google_control(page):
        return False
    if KEY_PATH_RE.search(page.url or ""):
        return True
    t = body_text(page).lower()
    if ("api key" in t or "secret key" in t or "personal access token" in t) \
            and looks_signed_in(page):
        return True
    return False


def reach_key_page(page, target: dict):
    """Step 5, click-based: press the signed-in shell's own key/token nav link (DOM study).

    Returns the PAGE where the action is -- the key page itself, or the login page the provider
    bounced us to (run_one runs the Google flow there). A NEW TAB counts (docs.inceptionlabs.ai
    opens its console with target=_blank). None when nothing was found.

    Falls back to the provider's documented apiKeyUrl / note URLs only when no on-page link
    leads there. Stock-path probing (/api-keys, /keys, ...) is gone with the rest of the URL
    guessing: it burned budget on pages that never existed and risked the IP.
    """
    if looks_like_key_page(page):
        return page   # already standing on it -- MEASURED on inception 2026-08-22: an instant
                      # consent redirect dropped the run straight onto /dashboard/api-keys and
                      # the old code still reported the provider a failure

    # A post-SSO /auth/login with a valid session is a bounce, not a wall (inception
    # measurement). Wait it out before judging -- but only when no password form is up.
    if login_wall(page) and not has_google_control(page):
        try:
            no_pw = not page.locator("input[type=password]").count()
        except Exception:
            no_pw = False
        if no_pw:
            await_login_bounce(page)
    if looks_like_key_page(page):
        return page

    for link in dom_nav_links(page, "keys"):
        follow = nav_click(page, link["href"])
        if follow is None:
            continue
        log(f"        clicking '{link['text']}' -> {follow.url}")
        if looks_like_key_page(follow):
            return follow
        if login_wall(follow) or has_google_control(follow):
            return follow   # the provider's own redirect answered the session question
        if follow is not page:
            try:
                follow.close()
            except Exception:
                pass
        else:
            step_back(page)

    tried: set[str] = set()
    for url in [target.get("apiKeyUrl"), *note_urls(target)]:
        url = (url or "").split("#")[0].rstrip("/")
        if not url or url in tried or url == (page.url or "").rstrip("/"):
            continue
        tried.add(url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            continue
        settle(page)
        dismiss_overlays(page)
        log(f"        documented entry point: {url}")
        if login_wall(page) or has_google_control(page):
            return page
        if looks_like_key_page(page):
            return page
    return None


def mint_key(page) -> tuple[Optional[str], str]:
    """Steps 6-7: create the key, then copy it. Returns (key or None, detail)."""
    before = keys_in(body_text(page))
    # Poll for the control to appear before clicking (wait_for_control docstring: the
    # featherless.ai measurement). Falls back to the broader substring matcher for icon buttons.
    clicked = wait_for_control(page, CREATE_LABELS, ms=15000) \
        or click_label(page, CREATE_LABELS, timeout=4000)
    if not clicked:
        dom = dom_study(page)
        btns = ", ".join(dom_button_names(dom))[:300]
        return None, (f"no create control found on the key page; visible buttons: "
                      f"{btns or '(none)'}")
    settle(page, 4000)

    # Many providers open a modal that asks for a NAME before the real create (operator,
    # 2026-08-22: "create api key will always ask for a name"). Fill the modal's name field
    # with the blueprint convention omniroute-auto-<timestamp>, THEN press the modal's own
    # create button. This is also the defect that made video_key_harvester stop one click
    # short on AI Studio.
    key_name = f"omniroute-auto-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        modal = page.locator("[role=dialog], .modal, [aria-modal=true]").first
        if modal.count() and modal.is_visible():
            for sel in ("input[placeholder*='name' i]", "input[aria-label*='name' i]",
                        "input[id*='name' i]", "input[type=text]", "input:not([type])"):
                box = modal.locator(sel).first
                try:
                    if box.count() and box.is_visible():
                        box.fill(key_name, timeout=3000)
                        clicked = f"{clicked} (named {key_name})"
                        break
                except Exception:
                    continue
            inner = click_label(page, ("create key", "create", "generate", "confirm",
                                      "create api key", "create secret key", "done", "submit"),
                                timeout=5000)
            if inner:
                clicked = f"{clicked} -> {inner}"
                settle(page, 4000)
    except Exception:
        pass

    txt = body_text(page)
    w = wall_page(page)
    if w:
        return None, w

    # Clipboard first: it is the only way to get a key a provider shows masked.
    if wait_for_control(page, COPY_LABELS, ms=8000) or click_label(page, COPY_LABELS, timeout=4000):
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
def run_one(ctx, api, target: dict, dry_run: bool, budget: int = 180) -> dict:
    global _deadline, _shot_prefix
    _deadline = time.monotonic() + budget
    slug = target["id"]
    _shot_prefix = slug
    name = target.get("name") or slug
    site = target.get("apiKeyUrl") or target.get("website")
    row: dict[str, Any] = {"provider": slug, "name": name, "url": site,
                           "card_stance": card_stance(target.get("freeNote", ""))}
    if not site:
        row.update(ok=False, stage="no-url", detail="catalog has no website for this provider")
        return row

    page = ctx.new_page()
    preexisting = frozenset(id(p) for p in _sibling_pages(page))
    try:
        try:
            page.goto(site, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            row.update(ok=False, stage="goto", detail=f"{type(exc).__name__}: {str(exc)[:120]}")
            return row
        settle(page)
        dropped = dismiss_overlays(page)
        if dropped:
            row["overlays_dismissed"] = dropped

        w = wall_page(page)
        if w:
            row.update(ok=False, stage="wall-on-landing", detail=w, shot=shot(page, f"{slug}-wall"))
            return row

        # Go where the keys are FIRST, and only sign in if the site actually asks. This is the
        # order a person uses, and it removes all guessing about session state: instead of
        # deciding "am I signed in?" from page furniture -- which produced a false positive on
        # sambanova's public pricing page -- we let the provider's own redirect answer it.
        # reach_key_page may move the action to a NEW TAB (target=_blank console links); adopt
        # that page so every later step works where the action actually is.
        def adopt(reached_page) -> bool:
            nonlocal page
            if reached_page is not None and reached_page is not page:
                try:
                    page.close()
                except Exception:
                    pass
                page = reached_page
            return reached_page is not None

        reached = adopt(reach_key_page(page, target))
        row["key_page_attempt"] = page.url

        if login_wall(page) or has_google_control(page) or not reached:
            sso = do_sso(ctx, page, target, target.get("google_email"))
            row["sso"] = sso
            follow = adopt_popup(ctx, page, preexisting)
            if follow is not page:
                try:
                    page.close()
                except Exception:
                    pass
                page = follow
            row["landed"] = page.url
            if sso in ("CAPTCHA_REFUSED", "PAYWALL_REFUSED", "IDENTITY_REFUSED",
                       "GOOGLE_REFUSED_AUTOMATION", "SITE_REFUSED"):
                row.update(ok=False, stage="wall-at-sso", detail=sso,
                           shot=shot(page, f"{slug}-sso"))
                return row
            # An odd SSO verdict does not overrule the page we are standing on: if the
            # provider's own redirects already dropped us on a key page, we are in (inception
            # measured exactly this). Only fail when the page disagrees too.
            if sso not in ("RETURNED", "ALREADY_SIGNED_IN") and not looks_like_key_page(page):
                row.update(ok=False, stage="sso", detail=sso, shot=shot(page, f"{slug}-sso"))
                return row
            reached = adopt(reach_key_page(page, target))

        if not reached or login_wall(page):
            row.update(ok=False, stage="find-key-page",
                       detail=("still behind a login wall after SSO" if login_wall(page)
                               else "no API-keys page found"),
                       shot=shot(page, f"{slug}-nokeypage"))
            return row
        row["key_page"] = page.url
        row["key_page_shot"] = shot(page, f"{slug}-keypage")   # proof the key page was reached

        w = wall_page(page)
        if w:
            row.update(ok=False, stage="wall-at-key-page", detail=w, shot=shot(page, f"{slug}-wall2"))
            return row

        # Wrong-console guard: NEVER mint a key from another provider's console and wire it
        # under this provider's name. MEASURED near-miss 2026-08-22: an orphaned inception
        # tab got adopted for featherless-ai and the run stood on the wrong /api-keys page.
        allowed_hosts = {host_of(target.get("apiKeyUrl") or "") ,
                         host_of(target.get("website") or "")} \
                        | {host_of(u) for u in note_urls(target)}
        allowed_hosts.discard("")
        page_host = host_of(page.url or "")
        if page_host and not any(same_site(page_host, a) for a in allowed_hosts):
            row.update(ok=False, stage="wrong-console",
                       detail=f"key page is on {page_host}, not this provider's site "
                              f"({', '.join(sorted(allowed_hosts))}); refusing to mint another "
                              f"provider's key under the {slug} name",
                       shot=shot(page, f"{slug}-wrongconsole"))
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


def context_dead(ctx) -> bool:
    """True when the persistent context can no longer open a page (Chrome died / was closed)."""
    try:
        p = ctx.new_page()
    except Exception:
        return True
    try:
        p.close()
    except Exception:
        pass
    return False


MAX_RELAUNCHES = 3


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
    ap.add_argument("--budget", type=int, default=180,
                    help="seconds per provider before moving on (default 180). Breadth first: "
                         "one slow site must not eat a sweep of 100+.")
    ap.add_argument("--headless", action="store_true",
                    help="not recommended: Google treats headless far more harshly")
    ap.add_argument("--attach", action="store_true",
                    help="attach to the ROBOT Chrome you started with HarvestChrome.cmd "
                         "(a real, non-automation-flagged browser) instead of launching one")
    ap.add_argument("--list", action="store_true", help="show the queue and exit")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright  # imported late: --list needs no browser

    targets = load_targets()
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        log("[-] OmniRoute login failed -- stopping before touching any provider")
        return 2
    have = {str(c.get("provider", "")).lower() for c in api.get_connections()}

    queue = [t for t in targets
             if t["id"].lower() not in have
             and t["id"] not in KNOWN_DEAD
             and t["id"] not in PARKED]
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
    relaunches = 0
    with sync_playwright() as pw:
        if args.attach:
            try:
                ctx = attach(pw)
                log(f"[*] attached to the robot Chrome on port {ROBOT_CDP_PORT} -- a real "
                    "browser you started, not an automation-flagged one")
            except Exception as exc:
                log(f"[-] could not attach on port {ROBOT_CDP_PORT}: {type(exc).__name__}: {exc}")
                log("    Double-click HarvestChrome.cmd first and LEAVE that Chrome open.")
                return 2
        else:
            ctx = launch(pw, args.headless)
        try:
            for i, t in enumerate(queue, 1):
                log(f"\n[{i}/{len(queue)}] {t['id']}  ({t.get('website') or 'no site'})")
                t = dict(t, google_email=args.google_email)
                try:
                    row = run_one(ctx, api, t, dry_run=args.dry_run or bool(args.probe),
                                  budget=args.budget)
                except Exception as exc:
                    row = {"provider": t["id"], "ok": False, "stage": "crash",
                           "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
                rows.append(row)
                mark = "WORKING" if row.get("ok") else f"no ({row.get('stage')})"
                log(f"        -> {mark}: {str(row.get('detail'))[:110]}")

                # THE 21:17 LESSON: one dead context must not burn the rest of the queue. That
                # run lost ~45 providers to instant TargetClosedError crashes because nothing
                # relaunched the browser. The profile is persistent, so a relaunch keeps every
                # session (they live in state/automation_profiles/providers, not the process).
                # The crashed provider is NOT retried -- the one-attempt rule stands; we move on.
                if not row.get("ok") and context_dead(ctx):
                    if relaunches >= MAX_RELAUNCHES:
                        log(f"\n[!] Chrome died again after {MAX_RELAUNCHES} relaunches -- "
                            "stopping the sweep honestly instead of looping on a dying browser.")
                        break
                    relaunches += 1
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    log(f"    [!] browser context died -- relaunching the robot profile "
                        f"(relaunch {relaunches}/{MAX_RELAUNCHES}); moving to the next provider")
                    try:
                        ctx = restart_attached(pw) if args.attach else launch(pw, args.headless)
                    except Exception as exc2:
                        log(f"    [-] relaunch failed: {exc2} -- stopping the sweep.")
                        break

                if row.get("detail") == "GOOGLE_REFUSED_AUTOMATION":
                    log("\n[!] Google refused the automated browser at the sign-in step.")
                    log("    Stopping the whole run. This is not worked around by design")
                    log("    (worklog #1033): no stealth patching, no fingerprint spoofing.")
                    break
                time.sleep(1.0)
        finally:
            if args.attach:
                # The Chrome window belongs to the operator; attach mode only ever
                # disconnects, never closes it.
                log("[*] harvest Chrome left open (attach mode) -- close it whenever you like")
            else:
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
