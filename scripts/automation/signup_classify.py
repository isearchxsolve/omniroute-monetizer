#!/usr/bin/env python3
"""Shared signup-state machine for the ordinary Google-SSO onboarding executors.

This module is the single source of truth for the acceptance taxonomy the
mandate (D:/conversations.txt, MASTER_WORKLOG.md #1404) requires. Both
niloy_sso_account_resolution.py and seat_signup_matrix.py import it so the
classification can never silently diverge between the two executors.

Terminal states
----------------
SSO_INITIATED
    Google chooser/consent was driven and the provider redirected, but the
    provider never returned to a usable surface (no redirect back to the
    provider in budget). SSO was genuinely *initiated*, but onboarding never
    completed to a usable account. Mid-flow evidence, NOT a completed signup.
SSO_PROVIDER_SESSION_OBSERVED
    The SSO redirect returned to the provider surface AND auth-like session
    cookies were independently observed on that surface -- but this is ONLY a
    provisional observation. Per the corrected Gate-1 taxonomy, auth-like
    cookies alone do NOT prove a new account was created. A new signup is only
    counted when, in addition, provider-specific account-creation evidence AND a
    successful harmless provider action are proven (see SIGNUP_COMPLETED).
ONBOARDING_VERIFICATION_REQUIRED
    SSO redirect completed and the provider now shows an onboarding /
    questionnaire / survey / loading / subscription / verification surface that
    must be completed (often by a human: email verification, profile
    questionnaire, plan selection) before a usable account exists. NOT success.
SIGNUP_COMPLETED
    The FULL chain is proven: (1) provider-specific account-creation evidence
    (e.g. an "account created" confirmation, a new-account welcome/onboarding
    gate the automation did not itself pass, or a fresh account record) AND (2)
    the provider reached its FINAL authenticated non-wall surface AND (3) one
    harmless provider action succeeded (e.g. send a message, open a model
    picker, list usage). Auth-like cookies alone are NOT sufficient.
EXISTING_ACCOUNT
    The provider surface was already authenticated before any SSO click. Not a
    new signup.
LOGIN_REQUIRED
    No usable path: no Google-SSO button, interactive re-auth demanded, SSO
    redirect returned to sign-in, or no protected session observed.
WALL
    The provider demands a hard wall (card / captcha / otp / email-verify) that
    automation must not bypass. Terminal evidence, not a stop for the mandate.

Strict rule applied everywhere: never count a SIGNUP_COMPLETED from screenshots,
cookie names, open tabs, model inventory, browser-only activity, or route
listings. The burden of proof is a real account-creation event + a confirmed
harmless provider action.
"""
import re

# Canonical set of every terminal state this module may emit. Validators and
# downstream aggregators import VALID_TERMINAL_STATES to reject unknown labels.
VALID_TERMINAL_STATES = {
    "SSO_INITIATED",
    "SSO_PROVIDER_SESSION_OBSERVED",
    "ONBOARDING_VERIFICATION_REQUIRED",
    "SIGNUP_COMPLETED",
    "EXISTING_ACCOUNT",
    "LOGIN_REQUIRED",
    "WALL",
}

SSO_PROVIDER_SESSION_OBSERVED = "SSO_PROVIDER_SESSION_OBSERVED"

# URL paths that prove the provider flow is still in onboarding, not a usable
# account. Onboarding/survey/questionnaire/verify-email surfaces are explicitly
# NOT a completed signup even when the page reports "signed in".
ONBOARDING_URL_RE = re.compile(
    r"/(onboarding|onboard|survey|questionnaire|welcome|getting-?started|"
    r"get-started|setup|complete-?profile|finish-?setup|verify-?(your-)?email|"
    r"confirm-?(your-)?email|activate|register|signup|sign-up|create-account|"
    r"join|invite|claim|profile-setup|account-setup)\b", re.I)

ONBOARDING_BODY_RE = re.compile(
    r"(complete your (profile|setup|account)|tell us (about you|more)|"
    r"verify your email|confirm your email|check your email|"
    r"finish (setting up|your account)|almost there|welcome aboard|"
    r"complete these steps|onboarding|questionnaire|"
    r"before you (can|start)|next steps|"
    r"(to continue|get the most out of))", re.I)

SIGNED_OUT_BODY_RE = re.compile(
    r"sign (in|up)|log ?in|create account|get started|continue with google|"
    r"sign up with google", re.I)

# Indicators that a provider surface is a real authenticated app/dashboard
# rather than a marketing/landing page. Used only as a soft corroboration when
# the URL is already known not to be an onboarding path.
DASHBOARD_BODY_RE = re.compile(
    r"(sign out|log out|dashboard|my (account|models|keys|api|workspace)|"
    r"generate|new (chat|project|video)|credits?|balance|billing|"
    r"your (models|tokens|usage))", re.I)


# Hard provider walls automation must never bypass. One shared pattern so the
# signup executors and the navigation harness cannot diverge on what counts as
# a wall (email verification, OTP, CAPTCHA, unusual-traffic, card, plan, quota).
WALL_BODY_RE = re.compile(
    r"verify your email|verification code|enter the code|captcha|"
    r"unusual traffic|check your email|confirm your email|otp|"
    r"add a (credit|debit) card|billing|upgrade your plan|choose a plan|"
    r"out of (free )?credits|quota exceeded|rate limit reached|"
    r"phone (number )?(verification|required)", re.I)


def body_is_hard_wall(body_low):
    """True when a provider surface text matches a hard, report-only wall."""
    return bool(WALL_BODY_RE.search(body_low or ""))


def final_url_is_onboarding(url):
    return bool(ONBOARDING_URL_RE.search(url or ""))


def classify_final_provider_state(url, body_low, auth_like_present,
                                  account_created_proof=False,
                                  provider_action_verified=False):
    """Classify the FINAL provider surface after an SSO redirect.

    Returns one of: ONBOARDING_VERIFICATION_REQUIRED, LOGIN_REQUIRED,
    SSO_PROVIDER_SESSION_OBSERVED, SIGNUP_COMPLETED.

    Per the corrected Gate-1 taxonomy, the presence of auth-like session cookies
    alone is NOT enough to count a new signup. It is only a provisional
    ``SSO_PROVIDER_SESSION_OBSERVED``. A ``SIGNUP_COMPLETED`` additionally
    requires both explicit provider account-creation evidence and a separately
    verified harmless provider action. These are independent verifier inputs;
    this classifier never infers either from a redirect, cookie, screenshot, or
    dashboard-looking body.
    """
    if final_url_is_onboarding(url) or ONBOARDING_BODY_RE.search(body_low or ""):
        return "ONBOARDING_VERIFICATION_REQUIRED"
    if SIGNED_OUT_BODY_RE.search(body_low or ""):
        return "LOGIN_REQUIRED"
    # Surface looks authenticated and a protected provider session was
    # independently observed (auth-like cookies). Without explicit proof that a
    # new account was created AND a harmless provider action succeeded, this is
    # only a provisional SSO/provider-session observation -- never a signup.
    if auth_like_present:
        if account_created_proof and provider_action_verified:
            return "SIGNUP_COMPLETED"
        return "SSO_PROVIDER_SESSION_OBSERVED"
    return "LOGIN_REQUIRED"


def classify_pre_sso_surface(url, body_low, auth_like_present):
    """Classify a provider surface observed BEFORE any SSO click was attempted.

    If it is already an authenticated dashboard, it is EXISTING_ACCOUNT (not a
    new signup). If it is an onboarding/questionnaire surface reached without SSO
    (e.g. a prior partial session), it is ONBOARDING_VERIFICATION_REQUIRED.
    """
    if final_url_is_onboarding(url) or ONBOARDING_BODY_RE.search(body_low or ""):
        return "ONBOARDING_VERIFICATION_REQUIRED"
    if SIGNED_OUT_BODY_RE.search(body_low or ""):
        return "LOGIN_REQUIRED"
    if auth_like_present:
        return "EXISTING_ACCOUNT"
    return "LOGIN_REQUIRED"
