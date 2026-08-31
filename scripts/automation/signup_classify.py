#!/usr/bin/env python3
"""Shared signup-state machine for the ordinary Google-SSO onboarding executors.

This module is the single source of truth for the acceptance taxonomy the
mandate (D:/conversations.txt, MASTER_WORKLOG.md #1404) requires. Both
niloy_sso_account_resolution.py and seat_signup_matrix.py import it so the
classification can never silently diverge between the two executors.

Terminal states
----------------
SSO_INITIATED
    We reached the Google account chooser / redirect, i.e. SSO was genuinely
    *initiated*, but the provider's own onboarding never completed to a usable
    account. This is mid-flow evidence, NOT a completed signup.
ONBOARDING_VERIFICATION_REQUIRED
    SSO redirect completed and the provider now shows an onboarding /
    questionnaire / survey surface that must be completed (often by a human:
    email verification, profile questionnaire, plan selection) before a usable
    account exists. NOT success.
SIGNUP_COMPLETED
    The provider reached its FINAL authenticated account/dashboard surface AND a
    protected provider session was independently verified (auth-like cookies on
    that final surface). Only then is a new signup counted.
EXISTING_ACCOUNT
    The provider surface was already authenticated before any SSO click. Not a
    new signup.
LOGIN_REQUIRED
    No usable path: no Google-SSO button, interactive re-auth demanded, SSO
    redirect returned to sign-in, or no protected session observed.
WALL
    The provider demands a hard wall (card / captcha / otp / email-verify) that
    automation must not bypass. Terminal evidence, not a stop for the mandate.
"""
import re

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


def final_url_is_onboarding(url):
    return bool(ONBOARDING_URL_RE.search(url or ""))


def classify_final_provider_state(url, body_low, auth_like_present):
    """Classify the FINAL provider surface after an SSO redirect.

    Returns one of: ONBOARDING_VERIFICATION_REQUIRED, LOGIN_REQUIRED,
    SIGNUP_COMPLETED.
    """
    if final_url_is_onboarding(url) or ONBOARDING_BODY_RE.search(body_low or ""):
        return "ONBOARDING_VERIFICATION_REQUIRED"
    if SIGNED_OUT_BODY_RE.search(body_low or ""):
        return "LOGIN_REQUIRED"
    # Surface looks authenticated. A completed signup additionally requires an
    # independently verified protected provider session (auth-like cookies).
    if auth_like_present:
        return "SIGNUP_COMPLETED"
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
