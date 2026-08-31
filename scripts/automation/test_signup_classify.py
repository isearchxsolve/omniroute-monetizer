#!/usr/bin/env python3
"""Focused unit tests for scripts/automation/signup_classify.py.

These verify the corrected Gate-1 taxonomy: auth-like cookies ALONE are
SSO_PROVIDER_SESSION_OBSERVED, and SIGNUP_COMPLETED requires explicit
account-creation proof. Run:  python scripts/automation/test_signup_classify.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import signup_classify as sc  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(f"FAIL: {msg}")
    print(f"PASS: {msg}")


def test_valid_states():
    check("SSO_PROVIDER_SESSION_OBSERVED" in sc.VALID_TERMINAL_STATES,
          "VALID_TERMINAL_STATES contains SSO_PROVIDER_SESSION_OBSERVED")
    check("SIGNUP_COMPLETED" in sc.VALID_TERMINAL_STATES,
          "VALID_TERMINAL_STATES contains SIGNUP_COMPLETED")


def test_auth_like_only_is_observed():
    # Auth-like cookies present, but no account-creation proof => OBSERVED, not COMPLETED
    state = sc.classify_final_provider_state(
        "https://app.chathub.gg/", "welcome to your dashboard", True)
    check(state == "SSO_PROVIDER_SESSION_OBSERVED",
          f"auth-like only -> SSO_PROVIDER_SESSION_OBSERVED (got {state})")


def test_completed_requires_proof():
    # Even with a clean final surface, no proof => still OBSERVED
    state = sc.classify_final_provider_state(
        "https://aymo.ai/chats", "your chats", True, account_created_proof=False)
    check(state == "SSO_PROVIDER_SESSION_OBSERVED",
          f"auth-like + no proof -> OBSERVED (got {state})")
    # Account creation alone is insufficient; the independent provider action
    # proof is a separate required input.
    state2 = sc.classify_final_provider_state(
        "https://aymo.ai/chats", "your chats", True, account_created_proof=True)
    check(state2 == "SSO_PROVIDER_SESSION_OBSERVED",
          f"account proof without action -> OBSERVED (got {state2})")
    state3 = sc.classify_final_provider_state(
        "https://aymo.ai/chats", "your chats", True,
        account_created_proof=True, provider_action_verified=True)
    check(state3 == "SIGNUP_COMPLETED",
          f"account proof + action proof -> SIGNUP_COMPLETED (got {state3})")


def test_onboarding():
    state = sc.classify_final_provider_state(
        "https://provider.com/onboarding", "complete your profile", True)
    check(state == "ONBOARDING_VERIFICATION_REQUIRED",
          f"onboarding surface -> ONBOARDING_VERIFICATION_REQUIRED (got {state})")


def test_signed_out():
    state = sc.classify_final_provider_state(
        "https://provider.com/login", "please sign in to your account", False)
    check(state == "LOGIN_REQUIRED",
          f"signed-out surface -> LOGIN_REQUIRED (got {state})")


def test_no_auth_no_proof():
    state = sc.classify_final_provider_state(
        "https://provider.com/whatever", "some app text", False)
    check(state == "LOGIN_REQUIRED",
          f"authenticated-looking body but no auth cookie -> LOGIN_REQUIRED (got {state})")


def test_pre_sso_existing():
    state = sc.classify_pre_sso_surface(
        "https://app.hyperbolic.ai/", "your models", True)
    check(state == "EXISTING_ACCOUNT",
          f"pre-SSO authenticated surface -> EXISTING_ACCOUNT (got {state})")


def main():
    test_valid_states()
    test_auth_like_only_is_observed()
    test_completed_requires_proof()
    test_onboarding()
    test_signed_out()
    test_no_auth_no_proof()
    test_pre_sso_existing()
    print("\nALL SIGNUP_CLASSIFY TESTS PASSED")


if __name__ == "__main__":
    main()
