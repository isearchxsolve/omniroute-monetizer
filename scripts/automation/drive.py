"""drive.py -- a browser I (the agent) drive by hand, one step at a time, recording as I go.

WHY THIS FILE EXISTS
--------------------
The operator's instruction, 2026-08-23:

    "the latest strategy is to take over the full control of the automation you take over
     the full control don't let the skip do it we work the way selenium test cases work
     actually selenium recording okay the qi tester records the whole flow test cases and
     then it captures in the test cases and then the selenium starts from there replaying
     the recording so we do that way you take over the control you do the full automation
     and then record it in the skip so that the next time the skip runs it runs flawlessly"

So: a QA tester records the flow once, by hand, watching the real page. The recording becomes
the test case. The runner just replays it. No guessing at replay time.

THE EVIDENCE THAT THIS IS THE RIGHT SHAPE
-----------------------------------------
The previous approach guessed at runtime -- guessed which URL held the login, guessed which
button was the door, guessed the label of the create-key control. MEASURED over a 50-provider
sweep, 2026-08-23:

    NO_SSO_CONTROL_FOUND  26 of 50      <-- guessing where the login lives, and missing
    goto failed            9
    mint (no create ctrl)  6
    find-key-page          5
    RETURNED (SSO worked)  3
    CAPTCHA/PAYWALL        3            <-- correctly refused, not solved
    browser died mid-sweep              <-- one shared context for 50 sites

Guessing was the single biggest loss. A recorded flow cannot guess wrong, because a human --
here, the agent looking at the real rendered page -- already found the right control once.

WHAT PROVED OUT AND MUST NOT BE RE-LITIGATED
--------------------------------------------
* Google's account chooser DOES render and DOES accept a click under Playwright, using the
  robot profile's existing session. MEASURED on sambanova 2026-08-22: the chooser listed one
  account and `isearch.xsolve@gmail.com` was selected. No password was typed, no MFA was
  touched, nothing was bypassed. Worklog #1033's "Google refuses Playwright" applies to
  signing IN from scratch, not to re-using a session that is already there.
* 3 providers reached RETURNED in the sweep -- the hand-off back from Google completes.

HOW I USE THIS
--------------
Chrome is launched ONCE and stays alive on a debug port, so it survives between my commands:

    drive.py start                          # launch Chrome on the robot profile
    drive.py rec nous-research              # start recording into recordings/<slug>.json
    drive.py open https://portal.nousresearch.com
    drive.py look                           # my eyes: URL, buttons, links, inputs, frames, walls
    drive.py click --role button --name "Continue with Google" --popup
    drive.py google --email isearch.xsolve@gmail.com
    drive.py look
    drive.py shot                           # when I need to actually SEE it
    drive.py key --role button --name "Create new key"
    drive.py save                           # close the recording

Every successful action appends a step to the recording. replay.py then re-runs those exact
steps for that provider, with no discovery logic at all.

SAFETY RULES BAKED IN (not optional, not overridable by a flag)
--------------------------------------------------------------
* The operator's live Chrome is NEVER opened. The profile comes from
  chrome_live_guard.safe_profile_dir("providers") and is checked with assert_safe(). The
  operator's rule, verbatim: "you never open an existing Chrome profile. You open a blank
  profile i signup with google, then you start harvesting."
* PASSWORDS ARE NEVER RECORDED AND NEVER TYPED. `fill` refuses any input[type=password] and
  refuses any value that arrives via a --password flag, because no such flag exists.
* CARD / CAPTCHA / PHONE walls are reported by `look` and are a STOP. The operator's rule,
  verbatim: "you reject, all paywall card requirements and all captcha. You do not hit them
  or hammer them." This file therefore has no solver, no retry loop, and no bypass.
* Secrets: a harvested key is written ONLY to the gitignored state/generated_keys.json. What
  is printed and what is recorded is a fingerprint (first 4, last 4, length) -- never the key.
  The recording stores HOW to get a key, never a key.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir  # noqa: E402
from chrome_no_discard import NO_DISCARD_FLAGS  # noqa: E402  -- stop Chrome discarding idle tabs

ROOT = pathlib.Path(__file__).resolve().parents[2]
# Recordings are TRACKED, not runtime state: they are the test cases the operator asked for
# ("record it in the skip so that the next time the skip runs it runs flawlessly"). state/ is
# gitignored, so keeping them there meant a clean checkout lost every recorded flow. They hold
# steps only -- never a key.
REC_DIR = ROOT / "recordings"
SHOT_DIR = ROOT / "state" / "harvest" / "shots"
CURRENT = ROOT / "state" / "_recording_current.json"
KEYS_FILE = ROOT / "state" / "generated_keys.json"
PROFILE_TAG = "providers"
# Chrome may already be up on the robot profile from an earlier session, on a port this file did
# not choose. MEASURED 2026-08-23: an instance was already serving the robot profile on 9333,
# so launching a second one on 9222 was silently refused by ProcessSingleton and the port never
# opened. Reuse beats relaunch: probe the known ports and attach to whatever is actually there.
CDP_PORTS = (9222, 9333, 9229, 9222)
CDP_PORT = 9222
CDP = f"http://127.0.0.1:{CDP_PORT}"


def probe_port(port: int, timeout: float = 2.0) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout).read()
        return True
    except Exception:
        return False


def discover_cdp() -> Optional[str]:
    """The endpoint of a live Chrome, or None. Honours DRIVE_CDP_PORT when set."""
    env = os.environ.get("DRIVE_CDP_PORT")
    order = ([int(env)] if env and env.isdigit() else []) + list(CDP_PORTS)
    for port in dict.fromkeys(order):
        if probe_port(port):
            return f"http://127.0.0.1:{port}"
    return None


CARD_HARD_RE = re.compile(
    r"card number|\bcvv\b|\bcvc\b|expiry date|expiration date|name on card|"
    r"add (?:a )?(?:credit |debit )?card|enter payment|billing address", re.I)
# Marketing, not a barrier -- only a wall when it sits in an open modal or beside a card form.
CARD_SOFT_RE = re.compile(
    r"credit card|payment method|upgrade to (?:pro|paid|premium)|start (?:your )?trial|"
    r"add a payment", re.I)
CARD_RE = re.compile(CARD_HARD_RE.pattern + "|" + CARD_SOFT_RE.pattern, re.I)

# A subscription gate on key CREATION itself. Deliberately narrow: the wording must tie a
# plan/subscription to making a key, so it cannot fire on a "Choose a plan" nav link, a pricing
# page, or the "Upgrade to Pro" advert that nearly every provider ships (see walls() for the
# false positive that cost us openadapter). MEASURED 2026-08-23 on featherless.ai, whose keys page
# is signed in, shows an enabled-looking "New API Key" button, and states plainly:
# "No API Keys -- Choose a plan to create API keys." The button is inert, so the only symptom
# without this check was a Playwright click timing out with no reason given.
PLAN_REQUIRED_RE = re.compile(
    r"(?:choose|select|pick) a (?:plan|subscription)[^.\n]{0,40}\b(?:to|before)\b[^.\n]{0,40}"
    r"(?:creat\w*|generat\w*|api key)|"
    r"(?:subscri\w+|paid plan|active plan|upgrade)[^.\n]{0,40}\brequired\b[^.\n]{0,40}"
    r"(?:api key|creat\w*)|"
    r"(?:api key|creat\w+ a key)[^.\n]{0,30}requires? (?:an? )?(?:paid |active )?"
    r"(?:plan|subscription)", re.I)
CAPTCHA_RE = re.compile(
    r"captcha|recaptcha|hcaptcha|turnstile|i'?m not a robot|verify you(?:'| a)re human|"
    r"unusual traffic|checking your browser", re.I)
# An actual challenge standing in the way -- these words only appear when a human is being asked
# to prove something.
CAPTCHA_HARD_RE = re.compile(
    r"i'?m not a robot|verify you(?:'| a)re human|unusual traffic|checking your browser|"
    r"solve the (?:captcha|challenge)|select all (?:images|squares)|type the (?:characters|code)",
    re.I)
# Boilerplate legal disclosure for INVISIBLE reCAPTCHA v3. Not a challenge and not a barrier.
# MEASURED 2026-08-23 on cloud.cerebras.ai, whose login page reads "This site is protected by
# reCAPTCHA and the Privacy Policy and Terms of Use apply." beneath a working GOOGLE button, with
# both the recaptcha and hcaptcha iframes present but is_visible()==False. v3 scores silently and
# never presents anything to solve, so there is nothing here to refuse or to hammer -- while the
# bare word "recaptcha" appears on a large share of provider login pages, so firing on it would
# walk away from most of the remaining catalog. Same mistake shape as reading "Upgrade to Pro" as
# a card wall. If a real challenge ever appears, CAPTCHA_HARD_RE or a VISIBLE widget catches it.
CAPTCHA_BADGE_RE = re.compile(
    r"protected by (?:google )?(?:recaptcha|hcaptcha|cloudflare)|"
    r"recaptcha and the (?:privacy policy|terms)", re.I)
PHONE_RE = re.compile(
    r"phone number|mobile number|verify your phone|sms code|whatsapp|wechat", re.I)
# Markers of a RENDERED SOURCE FILE rather than page copy. See looks_like_code().
CODE_TEXT_RE = re.compile(
    r"\"use strict\"|'use strict'|\bfunction\s*\(|=>\s*\{|\bvar\s+\w+\s*=|module\.exports|"
    r"sourceMappingURL|webpackJsonp|/\*!", re.I)
KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{30,}|SG_[A-Za-z0-9]{12,}|"
    r"nvapi-[A-Za-z0-9_\-]{16,}|gsk_[A-Za-z0-9]{20,}|r8_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}|"
    r"[A-Za-z0-9_\-]{28,})\b")


def out(msg: str = "") -> None:
    print(msg, flush=True)


def fingerprint(k: str) -> str:
    k = (k or "").strip()
    return f"{k[:4]}...{k[-4:]} (len={len(k)})" if len(k) >= 12 else f"(len={len(k)})"


# ---------------------------------------------------------------------------- recording state

# replay.py sets this False. A replay that appends to the recording it is replaying would grow
# the test case by one step every run -- MEASURED once on reka, which gained a 7th step.
RECORDING_ENABLED = True


def rec_load() -> Optional[dict]:
    if not CURRENT.exists():
        return None
    try:
        cur = json.loads(CURRENT.read_text(encoding="utf-8"))
    except Exception:
        return None
    path = REC_DIR / f"{cur['slug']}.json"
    if not path.exists():
        return {"slug": cur["slug"], "steps": [], "path": str(path)}
    d = json.loads(path.read_text(encoding="utf-8"))
    d["path"] = str(path)
    return d


def rec_save(d: dict) -> None:
    path = pathlib.Path(d.pop("path"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=2), encoding="utf-8")
    d["path"] = str(path)


def rec_step(action: str, **kw) -> None:
    """Append one replayable step. Silently does nothing when not recording."""
    if not RECORDING_ENABLED:
        return          # replay.py turns this off: replaying must never edit the test case
    d = rec_load()
    if d is None:
        return
    step = {"action": action, **{k: v for k, v in kw.items() if v is not None}}
    d.setdefault("steps", []).append(step)
    rec_save(d)
    out(f"    [rec {len(d['steps']):>2}] {action} " +
        " ".join(f"{k}={v!r}" for k, v in step.items() if k != "action"))


# ---------------------------------------------------------------------------- chrome / cdp


def find_chrome() -> pathlib.Path:
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        p = pathlib.Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if p.exists():
            return p
    raise SystemExit("Chrome not found in Program Files or LocalAppData")


def start_chrome() -> int:
    live = discover_cdp()
    if live:
        out(f"[+] reusing the Chrome already serving the robot profile at {live}")
        out("    (not launching a second one: ProcessSingleton would refuse it anyway)")
        return 0
    udd = safe_profile_dir(PROFILE_TAG)
    assert_safe(udd, who="drive.py")          # cannot ever be the operator's live Chrome
    chrome = find_chrome()
    # Fully detach. Without DETACHED_PROCESS the launching shell waits on Chrome and the
    # command appears to hang forever. Chrome must outlive this process: that is the whole
    # point -- it stays up between my commands so the session and page state persist.
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(chrome),
         f"--user-data-dir={udd}",
         f"--remote-debugging-port={CDP_PORT}",
         "--remote-allow-origins=*",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         *NO_DISCARD_FLAGS,
         "--window-size=1400,950", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        creationflags=flags, close_fds=True)
    out(f"[*] Chrome starting on {CDP}")
    out(f"    profile: {udd}   (robot profile -- the live one is untouched)")
    import urllib.request
    for _ in range(25):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{CDP}/json/version", timeout=2).read()
            out("[+] debug port is up")
            return 0
        except Exception:
            continue
    out("[-] debug port never came up")
    return 1


class Sess:
    """A short-lived Playwright attachment to the long-lived Chrome."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright
        endpoint = discover_cdp()
        if endpoint is None:
            raise SystemExit(f"no Chrome debug port answering on {CDP_PORTS}.\n"
                             f"run:  drive.py start")
        self.endpoint = endpoint
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(endpoint, timeout=20000)
        except Exception as exc:
            self._pw.stop()
            raise SystemExit(f"cannot attach to Chrome on {endpoint}: {exc}")
        self.ctx = self.browser.contexts[0]
        try:
            self.ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

    @property
    def pages(self) -> list:
        return [p for p in self.ctx.pages]

    def page(self):
        ps = self.pages
        if not ps:
            return self.ctx.new_page()
        for p in reversed(ps):            # prefer the newest real page over about:blank
            if p.url and p.url != "about:blank":
                return p
        return ps[-1]

    def close(self) -> None:
        try:
            self.browser.close()          # detaches; Chrome itself keeps running
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass


def frames_of(page) -> list:
    fs = [page.main_frame]
    try:
        fs += [f for f in page.frames if f is not page.main_frame]
    except Exception:
        pass
    return fs


def frame_showing(fr) -> bool:
    """Is this frame really on screen? The main frame always is; a child only if its <iframe>
    element -- and every iframe element above it -- is visible.

    MEASURED 2026-08-23 on api.together.ai AFTER the purchase dialog had been closed: a leftover
    hidden Stripe frame still held a nested iframe[src*='js.stripe.com'] that reported
    is_visible() == True, because Playwright resolves visibility inside the child frame's own
    coordinate space and knows nothing about the hidden ancestor holding it. card_form_present()
    therefore reported CARD on a page with no card form on it at all -- and since Stripe.js is
    loaded by a large share of providers, that is a permanent bogus refusal, i.e. free keys thrown
    away over a vendor script.
    """
    depth = 0
    while fr is not None and depth < 8:      # depth guard: never let a bad chain hang the run
        try:
            parent = fr.parent_frame
        except Exception:
            return False
        if parent is None:
            return True                      # walked all the way up to the main frame
        try:
            if not fr.frame_element().is_visible(timeout=400):
                return False
        except Exception:
            return False                     # detached mid-check -> not on screen
        fr = parent
        depth += 1
    return True


def looks_like_code(t: str) -> bool:
    """True when this "body text" is really a rendered source file, not page copy.

    MEASURED 2026-08-23 on api.together.ai: a js.stripe.com bundle was loaded AS a document inside
    an iframe, so the browser rendered 605,964 characters of minified JavaScript as body text. That
    made it the longest text on the page, so body_text() returned it and walls() matched the
    literals `hcaptcha` and "Verify Phone Number" INSIDE THE SOURCE -- reporting a CAPTCHA gate and
    a phone gate on a page that has neither. Refusing a provider because of a string in a vendor's
    minified bundle is the worst class of mistake available here: it is silent, and it looks
    principled.
    """
    if len(t) < 2000:
        return False
    head = t[:4000]
    if not CODE_TEXT_RE.search(head):
        return False
    # Prose separates words with spaces; minified code separates tokens with punctuation.
    return sum(head.count(c) for c in "{}();=>,:") > head.count(" ")


def body_text(page) -> str:
    """The longest body text that a human could actually be looking at."""
    best = ""
    for fr in frames_of(page):
        try:
            t = fr.inner_text("body", timeout=2500) or ""
        except Exception:
            continue
        if len(t) <= len(best):
            continue                         # cheap test first: skip the costly checks below
        if fr is not page.main_frame and not frame_showing(fr):
            continue
        if looks_like_code(t):
            continue
        best = t
    return best


def card_form_present(page) -> str:
    """A real card-entry surface on the page, or "". Not marketing copy -- an actual form."""
    sels = ("input[autocomplete*='cc-']", "input[name*='card']", "input[id*='cardnumber']",
            "input[placeholder*='card number' i]", "input[name*='cvc']", "input[name*='cvv']",
            "iframe[src*='js.stripe.com']", "iframe[src*='checkout.stripe.com']",
            "iframe[title*='card' i]", "iframe[name*='__privateStripe']",
            "iframe[src*='paddle']", "iframe[src*='razorpay']")
    for fr in frames_of(page):
        if fr is not page.main_frame and not frame_showing(fr):
            continue                          # a card field inside a HIDDEN iframe is not a wall
        for sel in sels:
            try:
                if fr.locator(sel).first.is_visible(timeout=400):
                    return sel
            except Exception:
                continue
    return ""


def dialog_text(page) -> str:
    """Text of any OPEN modal/dialog only. An upsell inside a modal blocks; a sidebar link does not."""
    chunks = []
    for fr in frames_of(page):
        if fr is not page.main_frame and not frame_showing(fr):
            continue                          # same ancestor-blindness as card_form_present()
        for sel in ("[role=dialog]", "[role=alertdialog]", "dialog[open]"):
            try:
                for node in fr.locator(sel).all()[:6]:
                    if node.is_visible(timeout=400):
                        chunks.append(node.inner_text(timeout=1200) or "")
            except Exception:
                continue
    return "\n".join(chunks)


def captcha_widget_visible(page) -> str:
    """A captcha a human is actually being shown, or "". Hidden v3 script frames don't count."""
    sels = ("iframe[src*='recaptcha/api2/anchor']", "iframe[src*='recaptcha/enterprise/anchor']",
            "iframe[src*='hcaptcha.com/captcha']", "iframe[src*='challenges.cloudflare.com']",
            "iframe[title*='recaptcha' i]", "iframe[title*='challenge' i]",
            ".g-recaptcha", ".h-captcha", ".cf-turnstile")
    for fr in frames_of(page):
        if fr is not page.main_frame and not frame_showing(fr):
            continue
        for sel in sels:
            try:
                if fr.locator(sel).first.is_visible(timeout=400):
                    return sel
            except Exception:
                continue
    return ""


DISMISS_RE = re.compile(
    r"^(?:close|cancel|skip|skip for now|not now|maybe later|later|no thanks|dismiss|continue|"
    r"got it|ok|okay|done|×|✕|x)$", re.I)


def dialog_dismissable(page) -> bool:
    """Does the open modal offer a way past it without paying?

    MEASURED 2026-08-23 on cloud.cerebras.ai straight after Google SSO: a modal announced "Your
    personal account has been migrated to a PayGo account. All your API keys, projects, and usage
    history are unchanged and safe. Add a payment method to get a free one-time $5 credit." There is
    no card form on the page, and the modal carries Close and CONTINUE. That is an ADVERT for a
    bonus, not a barrier -- Cerebras' free tier still works -- yet CARD_SOFT_RE saw "Add a payment"
    inside an open dialog and refused the provider outright, which would have thrown away one of the
    best free tiers in the catalog. Same family as the "Upgrade to Pro" sidebar advert that nearly
    cost us openadapter, one layer deeper.

    A genuine wall has no free path: no dismissal, or a real card form (card_form_present() catches
    that independently and is NOT softened by this).
    """
    for fr in frames_of(page):
        if fr is not page.main_frame and not frame_showing(fr):
            continue
        for dsel in ("[role=dialog]", "[role=alertdialog]", "dialog[open]"):
            try:
                for node in fr.locator(dsel).all()[:6]:
                    if not node.is_visible(timeout=400):
                        continue
                    for b in node.locator("button, [role=button], a").all()[:40]:
                        try:
                            if not b.is_visible():
                                continue
                            label = (b.inner_text(timeout=600) or
                                     b.get_attribute("aria-label") or "").strip()
                            if DISMISS_RE.match(label):
                                return True
                        except Exception:
                            continue
            except Exception:
                continue
    return False


def walls(txt: str, page=None) -> list[str]:
    """The three things this tool refuses to touch, in the operator's words: "you reject, all
    paywall card requirements and all captcha. You do not hit them or hammer them."

    The refusal must be accurate or it destroys the run. MEASURED 2026-08-23 on openadapter: the
    old text-only check raised CARD from the sidebar link "Upgrade to Pro -- More requests, faster
    models" on a page that was already signed in and had a working "+ new key" button. Refusing
    there would have thrown away a free key over an advert, and nearly every provider ships that
    advert. So an upsell PHRASE alone is not a wall. A wall is: a real card form, or that phrase
    inside an OPEN MODAL that is actually standing between us and the key.
    """
    hit = []
    if CAPTCHA_HARD_RE.search(txt):
        hit.append("CAPTCHA")
    elif page is not None:
        if captcha_widget_visible(page):
            hit.append("CAPTCHA")
    elif CAPTCHA_RE.search(txt) and not CAPTCHA_BADGE_RE.search(txt):
        # Text-only caller: stay cautious, but never on the invisible-v3 disclosure alone.
        hit.append("CAPTCHA")
    if PHONE_RE.search(txt):
        hit.append("PHONE")

    if CARD_HARD_RE.search(txt):
        hit.append("CARD")
    elif page is not None:
        sel = card_form_present(page)
        if sel:
            hit.append("CARD")
        elif CARD_SOFT_RE.search(dialog_text(page)) and not dialog_dismissable(page):
            hit.append("CARD")
    elif CARD_SOFT_RE.search(txt):
        # No page to inspect (text-only caller): keep the old, cautious reading.
        hit.append("CARD")

    # A subscription gate is not a card form and not an advert -- it is a hard stop with no free
    # path behind it, and it must be reported as such rather than as a mystery timeout.
    if PLAN_REQUIRED_RE.search(txt):
        hit.append("PLAN")
    return hit


# ---------------------------------------------------------------------------- commands


def cmd_look(s: Sess, limit: int = 30, grep: Optional[str] = None) -> int:
    """My eyes. Compact enough to read, complete enough to pick a real selector from."""
    page = s.page()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    txt = body_text(page)
    out(f"URL    {page.url}")
    try:
        out(f"TITLE  {page.title()}")
    except Exception:
        pass
    w = walls(txt, page)
    out(f"WALLS  {' '.join(w) if w else 'none'}"
        + ("   <-- STOP: refuse, do not solve" if w else ""))
    if len(s.pages) > 1:
        out(f"PAGES  {len(s.pages)}: " + " | ".join(
            f"[{i}] {p.url[:60]}" for i, p in enumerate(s.pages)))

    pat = re.compile(grep, re.I) if grep else None
    for fi, fr in enumerate(frames_of(page)):
        tag = "" if fi == 0 else f" (frame {fi}: {fr.url[:50]})"
        for role in ("button", "link", "textbox", "combobox"):
            try:
                items = fr.get_by_role(role).all()
            except Exception:
                continue
            shown = []
            for el in items[:120]:
                try:
                    if not el.is_visible():
                        continue
                    name = (el.get_attribute("aria-label")
                            or el.inner_text(timeout=800) or "").strip()
                    name = re.sub(r"\s+", " ", name)[:70]
                    if not name:
                        name = (el.get_attribute("placeholder")
                                or el.get_attribute("name") or "").strip()[:70]
                    if pat and not pat.search(name):
                        continue
                    if name:
                        shown.append(name)
                except Exception:
                    continue
            if shown:
                out(f"--- {role}{tag} ({len(shown)})")
                for n in shown[:limit]:
                    out(f'    "{n}"')
    try:
        for inp in page.locator("input").all()[:limit]:
            if not inp.is_visible():
                continue
            t = inp.get_attribute("type") or "text"
            out(f"    input[type={t}] name={inp.get_attribute('name')!r} "
                f"placeholder={inp.get_attribute('placeholder')!r}"
                + ("   <-- NEVER filled by this tool" if t == "password" else ""))
    except Exception:
        pass
    keys = [k for k in KEY_RE.findall(txt) if len(k) >= 20][:3]
    if keys:
        out(f"KEYLIKE on page: {', '.join(fingerprint(k) for k in keys)}")
    return 0


def resolve(page, role: Optional[str], name: Optional[str], css: Optional[str],
            frame: Optional[int], exact: bool = False):
    frs = frames_of(page)
    targets = [frs[frame]] if frame is not None and frame < len(frs) else frs
    for fr in targets:
        try:
            if css:
                loc = fr.locator(css).first
            elif role and name:
                loc = fr.get_by_role(
                    role, name=(name if exact else re.compile(re.escape(name), re.I))).first
            elif name:
                loc = fr.get_by_text(re.compile(re.escape(name), re.I)).first
            else:
                continue
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def cmd_open(s: Sess, url: str) -> int:
    page = s.page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    rec_step("goto", url=url)
    return cmd_look(s)


def cmd_click(s: Sess, role, name, css, frame, popup: bool, exact: bool) -> int:
    page = s.page()
    loc = resolve(page, role, name, css, frame, exact)
    if loc is None:
        out(f"[-] not found: role={role} name={name!r} css={css}")
        return 4
    before = len(s.pages)
    if popup:
        try:
            with s.ctx.expect_page(timeout=12000) as pi:
                loc.click(timeout=10000)
            p = pi.value
            p.wait_for_load_state("domcontentloaded", timeout=20000)
            out(f"[+] popup opened: {p.url[:100]}")
        except Exception as exc:
            out(f"[!] no popup ({type(exc).__name__}); it may have navigated in this tab")
    else:
        loc.click(timeout=10000)
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        page.wait_for_timeout(1200)
    rec_step("click", role=role, name=name, css=css, frame=frame,
             popup=(True if popup else None), exact=(True if exact else None))
    if len(s.pages) != before:
        out(f"[*] page count {before} -> {len(s.pages)}")
    return cmd_look(s)


def cmd_fill(s: Sess, css: str, value: str) -> int:
    page = s.page()
    loc = page.locator(css).first
    if not loc.count():
        out(f"[-] not found: {css}")
        return 4
    if (loc.get_attribute("type") or "").lower() == "password":
        out("[-] REFUSED: this tool never types into a password field. "
            "The Google session is already in the robot profile; no password is needed.")
        return 5
    loc.fill(value, timeout=8000)
    rec_step("fill", css=css, value=value)
    return 0


def cmd_press(s: Sess, key: str) -> int:
    s.page().keyboard.press(key)
    rec_step("press", key=key)
    return cmd_look(s)


def cmd_google(s: Sess, email: Optional[str]) -> int:
    """Pick the account on Google's chooser, then follow through to the provider.

    No password is ever typed. If Google shows a password box, that means the robot profile
    has no live session for that account and the honest answer is to stop and say so.
    """
    page = None
    for p in s.pages:
        if "accounts.google.com" in (p.url or ""):
            page = p
            break
    if page is None:
        out("[-] no Google page open. Click 'Continue with Google' first.")
        return 4
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass

    if page.locator("input[type=password]").count():
        out("[-] STOP: Google is asking for a PASSWORD, so this profile has no live session.")
        out("    Nothing is typed. Sign in once by hand (SignInWithGoogleOnce.cmd), then retry.")
        return 6
    if CAPTCHA_RE.search(body_text(page)):
        out("[-] STOP: CAPTCHA on the Google page. Refused, not solved.")
        return 7

    tiles = []
    for sel in ("div[data-identifier]", "li[class*=aZvCDf]", "div[data-email]",
                "[role=link][data-identifier]"):
        try:
            got = page.locator(sel).all()
            if got:
                tiles = got
                break
        except Exception:
            continue
    picked = None
    if tiles:
        out(f"[*] chooser shows {len(tiles)} account(s)")
        for t in tiles:
            ident = (t.get_attribute("data-identifier") or t.get_attribute("data-email")
                     or (t.inner_text(timeout=800) or "")).strip()
            out(f'      "{re.sub(chr(10), " / ", ident)[:70]}"')
            if picked is None and (not email or (email.lower() in ident.lower())):
                picked = (t, ident)
        if picked is None:
            out(f"[-] {email!r} is not on the chooser. Not guessing another account.")
            return 8
        out(f"[*] picking {picked[1].splitlines()[0][:50]}")
        picked[0].click(timeout=10000)
    elif email:
        loc = page.get_by_text(re.compile(re.escape(email), re.I)).first
        if not loc.count():
            out("[-] no chooser tiles and no matching email text on the page.")
            return 8
        loc.click(timeout=10000)
    else:
        out("[-] no chooser tiles found; pass --email to target one.")
        return 8

    waited = 0
    while waited < 40000:
        cur = [p for p in s.pages if not p.is_closed()]
        if not any("accounts.google.com" in (p.url or "") for p in cur):
            out("[+] Google handed back to the provider")
            rec_step("google", email=email)
            return cmd_look(s)
        gp = next(p for p in cur if "accounts.google.com" in (p.url or ""))
        if "signin/rejected" in gp.url:
            out("[-] STOP: Google refused this client (signin/rejected). Not patched around.")
            return 9
        for lbl in ("continue", "allow", "confirm", "next"):
            b = gp.get_by_role("button", name=re.compile(lbl, re.I)).first
            try:
                if b.count() and b.is_visible():
                    out(f"[*] consent: pressing {lbl!r}")
                    b.click(timeout=5000)
                    break
            except Exception:
                continue
        gp.wait_for_timeout(1500)
        waited += 1500
    out("[-] still on Google after 40s")
    return 10


def cmd_key(s: Sess, role, name, css, frame, slug: Optional[str]) -> int:
    """Press the create-key control, then capture the key: clipboard first, then the page."""
    page = s.page()
    before = set(KEY_RE.findall(body_text(page)))
    if role or name or css:
        loc = resolve(page, role, name, css, frame)
        if loc is None:
            out(f"[-] create control not found: role={role} name={name!r} css={css}")
            return 4
        loc.click(timeout=10000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            page.wait_for_timeout(2000)
        rec_step("click", role=role, name=name, css=css, frame=frame)

    w = walls(body_text(page), page)
    if w:
        out(f"[-] STOP: {' '.join(w)} appeared. Refused, not solved.")
        return 7

    key = None
    for lbl in ("copy", "copy key", "copy api key", "copy to clipboard"):
        b = resolve(page, "button", lbl, None, None)
        if b is None:
            continue
        try:
            b.click(timeout=5000)
            page.wait_for_timeout(600)
            got = (page.evaluate("navigator.clipboard.readText()") or "").strip()
            if KEY_RE.fullmatch(got or "") or (got and len(got) >= 20):
                key = got
                out(f"[+] key from clipboard via {lbl!r}: {fingerprint(key)}")
                rec_step("copy", role="button", name=lbl)
                break
        except Exception:
            continue
    if key is None:
        fresh = [k for k in KEY_RE.findall(body_text(page)) if k not in before and len(k) >= 20]
        if fresh:
            key = fresh[0]
            out(f"[+] key read from page: {fingerprint(key)}")
            rec_step("read_key_from_page")
    if key is None:
        out("[-] no key captured. Use `look` and pick the copy/reveal control explicitly.")
        return 11

    slug = slug or (rec_load() or {}).get("slug")
    if slug:
        KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        store = {}
        if KEYS_FILE.exists():
            try:
                store = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            except Exception:
                store = {}
        store[slug] = key
        KEYS_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")
        out(f"[+] stored under {slug!r} in state/generated_keys.json (gitignored)")
        out("    the recording holds only HOW to get a key, never the key itself")
    return 0


def store_key(slug: Optional[str], key: str) -> None:
    """Raw key -> gitignored state/generated_keys.json ONLY. Never the recording, never stdout."""
    if not slug:
        return
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    store = {}
    if KEYS_FILE.exists():
        try:
            store = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except Exception:
            store = {}
    store[slug] = key
    KEYS_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")
    out(f"[+] stored under {slug!r} in state/generated_keys.json (gitignored)")


STRONG_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{30,}|SG_[A-Za-z0-9]{12,}|"
    r"nvapi-[A-Za-z0-9_\-]{16,}|gsk_[A-Za-z0-9]{20,}|r8_[A-Za-z0-9]{20,})\b")


def pick_key(txt: str) -> str:
    """The most key-like string on a page, or "".

    A recognisable prefix (sk-, gsk_, nvapi-, ...) beats a bare long token, because KEY_RE's
    catch-all `[A-Za-z0-9_-]{28,}` branch also matches build hashes, CSS class soup and CSP
    nonces, and findall returns them in page order rather than in order of confidence.
    """
    strong = STRONG_KEY_RE.findall(txt)
    if strong:
        return max(strong, key=len)
    loose = [k for k in KEY_RE.findall(txt) if len(k) >= 24]
    return max(loose, key=len) if loose else ""


def wait_for_key(page, ms: int = 15000) -> str:
    """Poll until a key-shaped string appears on the page, or time out.

    MEASURED 2026-08-23 on openadapter: reading immediately after the create button returned
    "no key-shaped text on the page" -- the row renders a beat later. Same shape as the reka
    step-1 failure. This is a WAIT, not a retry: nothing is clicked twice.
    """
    waited = 0
    while True:
        got = pick_key(body_text(page))
        if got:
            return got
        if waited >= ms:
            return ""
        page.wait_for_timeout(1000)
        waited += 1000


def cmd_readkey(s: Sess, slug: Optional[str]) -> int:
    """Take the key straight out of the rendered page.

    Preferred over the clipboard whenever the provider actually shows the value -- MEASURED on
    openadapter, which reveals the newly created key in the DOM. No clipboard means no stale-read
    race at all.
    """
    page = s.page()
    got = wait_for_key(page)
    if not got:
        out("[-] no key-shaped text on the page")
        return 11
    out(f"[+] key from page: {fingerprint(got)}")
    store_key(slug or (rec_load() or {}).get("slug"), got)
    rec_step("read_key_from_page")
    return 0


def poison_clipboard(page) -> str:
    """Put a sentinel on the clipboard so a later read cannot silently return STALE content.

    MEASURED 2026-08-23 on openadapter: replay clicked "copy" on the freshly created key, read the
    clipboard, and got the PREVIOUS key back -- the read beat the page's clipboard write. It looked
    like a success because the stale value happened to be our own earlier key. On any other
    provider that is a wrong key attributed to a real account, which is exactly the false
    "harvested" claim the rules forbid. So: mark the clipboard first, then require it to change.
    """
    mark = "OMNIROUTE-CLIPBOARD-SENTINEL"
    try:
        page.evaluate("m => navigator.clipboard.writeText(m)", mark)
        return mark
    except Exception:
        pass
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{mark}'"],
                       capture_output=True, text=True, timeout=15)
        return mark
    except Exception:
        return ""


def read_clipboard(page) -> str:
    try:
        got = (page.evaluate("navigator.clipboard.readText()") or "").strip()
        if got:
            return got
    except Exception:
        pass
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def cmd_clip(s: Sess, slug: Optional[str], sentinel: str = "", wait_ms: int = 8000) -> int:
    """Read the clipboard after a provider's own copy control put a key there.

    Many providers mask the key in the list and only ever hand over the full value through
    their copy button -- MEASURED on platform.reka.ai, which shows `6de00606****2a98` and
    nothing else. So the clipboard is not a shortcut here, it is the only channel.

    When `sentinel` is given, the value MUST differ from it: see poison_clipboard() for the stale
    read that made this necessary.
    """
    page = s.page()
    got = ""
    waited = 0
    while True:
        got = read_clipboard(page)
        if got and got != sentinel:
            break
        if waited >= wait_ms:
            break
        page.wait_for_timeout(500)
        waited += 500
    if sentinel and got == sentinel:
        out("[-] the copy control never wrote to the clipboard (still the sentinel) -- "
            "refusing to report a stale key")
        return 11
    if not got:
        out("[-] clipboard is empty")
        return 11
    if len(got) < 16 or "\n" in got.strip():
        out(f"[-] clipboard does not look like a key: {fingerprint(got)}")
        return 11
    out(f"[+] key from clipboard: {fingerprint(got)}")
    store_key(slug or (rec_load() or {}).get("slug"), got)
    rec_step("clipboard_key")
    return 0


def cmd_copy(s: Sess, role, name, css, frame, exact: bool, slug: Optional[str]) -> int:
    """Click a NAMED copy control, then take what it put on the clipboard. Records one `copy` step.

    cmd_key() already handles the easy shape: one copy button whose label is literally "copy".
    MEASURED 2026-08-23 on portal.nousresearch.com, which is not that shape -- the key is masked
    in the table (`sk-nous-...ZrkL`) and every row carries an identical icon button whose only
    accessible name is title="Copy to clipboard". Resolving that by name picks the FIRST row, i.e.
    a key from June, while the key just minted sits in the last row. Copying the wrong account's
    key and calling it harvested is precisely the false claim the rules forbid, so the control has
    to be addressable by selector.

    The clipboard is marked before the click and the value must change -- see poison_clipboard().
    """
    page = s.page()
    sentinel = poison_clipboard(page)
    loc = resolve(page, role, name, css, frame, exact)
    if loc is None:
        out(f"[-] copy control not found: role={role} name={name!r} css={css}")
        return 4
    loc.click(timeout=10000)
    page.wait_for_timeout(600)
    rc = cmd_clip(s, slug, sentinel=sentinel)
    if rc != 0:
        return rc
    # cmd_clip recorded "clipboard_key"; replace it with a "copy" step carrying this control, so
    # replay clicks it itself (and poisons the clipboard first) instead of reading a stale value.
    rec = rec_load()
    if rec and rec.get("steps") and rec["steps"][-1].get("action") == "clipboard_key":
        rec["steps"].pop()
        rec_save(rec)
        rec_step("copy", role=role, name=name, css=css, frame=frame, exact=exact or None)
    return 0


def cmd_wire(slug: str) -> int:
    """Wire the captured key into OmniRoute and PROVE it with a real completion.

    Reuses harvest_free_keys.wire() on purpose: that function already carries the policy this
    project settled on -- create the row WITH the key (OmniRoute rejects a keyless row with
    400 "API key is required"), run OmniRoute's own test, then demand that a real model answer
    a real question, and DELETE the row if it cannot. OmniRoute reporting valid=True is not
    proof; uncloseai passed that test and every one of its models 404'd.
    """
    if not KEYS_FILE.exists():
        out("[-] no state/generated_keys.json yet")
        return 2
    store = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    key = store.get(slug)
    if not key:
        out(f"[-] no key stored for {slug!r}. Captured keys: {sorted(store)}")
        return 2
    import harvest_free_keys as H
    from oauth_keepalive import resolve_password
    from omniroute_api import OmniRouteAPI
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        out("[-] OmniRoute login failed; nothing changed")
        return 2
    out(f"[*] wiring {slug} with {fingerprint(key)}")
    res = H.wire(api, slug, slug, key)
    if res.get("ok"):
        out(f"[+] WIRED AND PROVEN: {slug} -- a real model answered. {res.get('detail')}")
        rec_step("wire", slug=slug)
        return 0
    out(f"[-] not wired ({res.get('stage')}): {res.get('detail')}")
    if res.get("deleted"):
        out("    the row was deleted again, so OmniRoute's router will not pick a dead backend")
    return 12


def cmd_shot(s: Sess, tag: str) -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = SHOT_DIR / f"drive-{tag}.png"
    s.page().screenshot(path=str(p), full_page=False)
    out(f"[+] {p}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="launch Chrome on the robot profile, with a debug port")
    sub.add_parser("stop", help="close that Chrome")
    r = sub.add_parser("rec", help="begin recording a provider's flow")
    r.add_argument("slug")
    r.add_argument("--fresh", action="store_true", help="discard any existing recording")
    sub.add_parser("save", help="finish the current recording")
    o = sub.add_parser("open", help="navigate")
    o.add_argument("url")
    lk = sub.add_parser("look", help="describe the page: controls, inputs, frames, walls")
    lk.add_argument("--limit", type=int, default=30)
    lk.add_argument("--grep", help="only show control names matching this")
    c = sub.add_parser("click")
    c.add_argument("--role")
    c.add_argument("--name")
    c.add_argument("--css")
    c.add_argument("--frame", type=int)
    c.add_argument("--popup", action="store_true", help="expect a new window (Google SSO)")
    c.add_argument("--exact", action="store_true")
    f = sub.add_parser("fill")
    f.add_argument("css")
    f.add_argument("value")
    pr = sub.add_parser("press")
    pr.add_argument("key")
    g = sub.add_parser("google", help="pick the account on Google's chooser")
    g.add_argument("--email")
    k = sub.add_parser("key", help="press create-key and capture the key")
    k.add_argument("--role")
    k.add_argument("--name")
    k.add_argument("--css")
    k.add_argument("--frame", type=int)
    k.add_argument("--slug")
    sh = sub.add_parser("shot")
    sh.add_argument("tag", nargs="?", default="now")
    cl = sub.add_parser("clip", help="capture a key the provider's copy button put on the clipboard")
    cl.add_argument("--slug")
    cp = sub.add_parser("copy", help="click a specific copy control, then take the key it copied")
    cp.add_argument("--role")
    cp.add_argument("--name")
    cp.add_argument("--css")
    cp.add_argument("--frame", type=int)
    cp.add_argument("--exact", action="store_true")
    cp.add_argument("--slug")
    rk = sub.add_parser("readkey", help="capture a key the provider prints on the page (no clipboard)")
    rk.add_argument("--slug")
    wr = sub.add_parser("wire", help="wire the captured key into OmniRoute and prove it")
    wr.add_argument("slug")
    args = ap.parse_args()

    if args.cmd == "start":
        return start_chrome()

    if args.cmd == "wire":
        return cmd_wire(args.slug)

    if args.cmd == "rec":
        REC_DIR.mkdir(parents=True, exist_ok=True)
        path = REC_DIR / f"{args.slug}.json"
        if args.fresh and path.exists():
            path.unlink()
        if not path.exists():
            path.write_text(json.dumps(
                {"slug": args.slug, "recorded_by": "agent via drive.py", "steps": []},
                indent=2), encoding="utf-8")
        CURRENT.write_text(json.dumps({"slug": args.slug}), encoding="utf-8")
        out(f"[+] recording -> {path}")
        return 0

    if args.cmd == "save":
        d = rec_load()
        if d is None:
            out("[-] nothing being recorded")
            return 2
        out(f"[+] {d['slug']}: {len(d.get('steps', []))} step(s) -> {d['path']}")
        for i, st in enumerate(d.get("steps", []), 1):
            out(f"    {i:>2}. {st['action']:<16} " +
                " ".join(f"{k}={v!r}" for k, v in st.items() if k != "action"))
        CURRENT.unlink(missing_ok=True)
        return 0

    s = Sess()
    try:
        if args.cmd == "stop":
            try:
                for p in s.pages:
                    p.close()
            except Exception:
                pass
            out("[+] Chrome closed")
            return 0
        if args.cmd == "open":
            return cmd_open(s, args.url)
        if args.cmd == "look":
            return cmd_look(s, args.limit, args.grep)
        if args.cmd == "click":
            return cmd_click(s, args.role, args.name, args.css, args.frame,
                             args.popup, args.exact)
        if args.cmd == "fill":
            return cmd_fill(s, args.css, args.value)
        if args.cmd == "press":
            return cmd_press(s, args.key)
        if args.cmd == "google":
            return cmd_google(s, args.email)
        if args.cmd == "key":
            return cmd_key(s, args.role, args.name, args.css, args.frame, args.slug)
        if args.cmd == "shot":
            return cmd_shot(s, args.tag)
        if args.cmd == "clip":
            return cmd_clip(s, args.slug)
        if args.cmd == "copy":
            return cmd_copy(s, args.role, args.name, args.css, args.frame,
                            args.exact, args.slug)
        if args.cmd == "readkey":
            return cmd_readkey(s, args.slug)
        return 2
    finally:
        s.close()


if __name__ == "__main__":
    raise SystemExit(main())
