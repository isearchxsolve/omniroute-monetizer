#!/usr/bin/env python3
"""Focused offline tests for scripts/automation/harness_all_tabs.py hardening.

No Chrome is launched, no CDP port is contacted, no service is touched: every
unit under test is a pure function or a fake-owner-driven pure path.

Run:  python scripts/automation/test_harness_all_tabs.py
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import harness_all_tabs as h  # noqa: E402
import signup_classify as sc  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(f"FAIL: {msg}")
    print(f"PASS: {msg}")


def test_taxonomy_single_source():
    # Terminal labels the harness can emit must all be canonical.
    for label in ("SSO_INITIATED", "SSO_PROVIDER_SESSION_OBSERVED",
                  "ONBOARDING_VERIFICATION_REQUIRED", "WALL", "LOGIN_REQUIRED",
                  "EXISTING_ACCOUNT"):
        check(h.sso_label_is_canonical(label), f"{label} is canonical")
        check(label in sc.VALID_TERMINAL_STATES,
              f"{label} present in shared VALID_TERMINAL_STATES")
    # Non-terminal helper labels are explicitly whitelisted.
    for label in ("SSO_NO_GOOGLE_BUTTON", "BUDGET_EXCEEDED"):
        check(h.sso_label_is_canonical(label), f"{label} allowed (non-terminal)")
    # Anything else must be rejected fail-closed.
    for label in ("SIGNED_IN", "already_signed_in", "NO_GOOGLE_BUTTON", ""):
        check(not h.sso_label_is_canonical(label),
              f"legacy label {label!r} rejected")


def test_wall_body_shared_regex():
    check(sc.body_is_hard_wall("please verify your email to continue"),
          "email-verify text detected as hard wall")
    check(sc.body_is_hard_wall("enter the captcha below"),
          "captcha text detected as hard wall")
    check(not sc.body_is_hard_wall("your chat history and models"),
          "normal dashboard text is not a wall")


def test_redirect_host_validation():
    # Google mid-flow always allowed.
    check(h.redirect_host_allowed(None, "grok.com", "https://accounts.google.com/o/oauth2/x"),
          "accounts.google.com redirect allowed")
    # Same registrable domain allowed (www / subdomain variants).
    check(h.redirect_host_allowed(None, "grok.com", "https://www.grok.com/login"),
          "same registrable-domain redirect allowed")
    check(not h.redirect_host_allowed(None, "console.groq.com",
                                      "https://api.together.ai/playground"),
          "different provider host rejected")
    # Cross-domain and empty URL rejected.
    check(not h.redirect_host_allowed(None, "duck.ai", "https://evil.example.com/cb"),
          "unrelated-host redirect rejected")
    check(not h.redirect_host_allowed(None, "duck.ai", ""),
          "empty redirect URL rejected")


def test_on_target_surface():
    check(h.on_target_surface("https://console.groq.com/playground",
                              "https://console.groq.com/playground"),
          "exact surface recognized")
    check(h.on_target_surface("https://console.groq.com/playground/x?y=1",
                              "https://console.groq.com/playground"),
          "path-under-surface recognized")
    check(h.on_target_surface("https://www.grok.com/", "https://grok.com/"),
          "registrable-domain match recognized")
    check(not h.on_target_surface("https://grok.com/get-started",
                                  "https://grok.com/chat"),
          "wrong path on same host rejected")
    check(not h.on_target_surface("https://evil.example.com/playground",
                                  "https://grok.com/chat"),
          "host swap rejected")


def test_safe_url_redacts_query():
    red = h.safe_url("https://provider.com/cb?code=supersecret&state=x")
    check("supersecret" not in red, "OAuth code redacted from URL")
    check(red.startswith("https://provider.com/cb"), "path preserved in redacted URL")


def test_apply_row_isolation_and_budget():
    # A row that raises must become ROW_ERROR; remaining rows still processed.
    # Budget already expired -> every row BUDGET_EXCEEDED without being driven.
    import time as _t

    plan = [{"site": "A", "action": "VERIFY_OR_NAVIGATE", "targetId": "t1",
             "to": "https://a.example/"},
            {"site": "B", "action": "REPORT_AUTH_WALL", "targetId": "t2",
             "to": ""}]

    calls = {"n": 0}

    def fake_tab_targets(owner):
        calls["n"] += 1
        raise RuntimeError("boom")

    orig = h.tab_targets
    h.tab_targets = fake_tab_targets
    try:
        results = h.apply_plan(plan, object(), wait=0.1,
                               budget=_t.monotonic() - 1.0)
        check(all(r["status"] == "BUDGET_EXCEEDED" for r in results),
              "expired budget marks rows BUDGET_EXCEEDED without driving")
        check(calls["n"] == 0, "expired budget drives nothing")
    finally:
        h.tab_targets = orig


def test_apply_row_error_continues():
    plan = [{"site": "A", "action": "VERIFY_OR_NAVIGATE", "targetId": "t1",
             "to": "https://a.example/"},
            {"site": "B", "action": "REPORT_AUTH_WALL", "targetId": "t2",
             "to": ""}]
    calls = {"n": 0}

    def fake_tab_targets(owner):
        calls["n"] += 1
        raise RuntimeError("boom")

    orig = h.tab_targets
    h.tab_targets = fake_tab_targets
    try:
        results = h.apply_plan(plan, object(), wait=0.1)
        check(results[0]["status"] == "ROW_ERROR", "row failure isolated as ROW_ERROR")
        check(results[1]["status"] == "REPORTED_ONLY",
              "later row still processed after earlier row failure")
        check(calls["n"] == 1, "row isolation stops per-row, not per-run")
    finally:
        h.tab_targets = orig


def main():
    test_taxonomy_single_source()
    test_wall_body_shared_regex()
    test_redirect_host_validation()
    test_on_target_surface()
    test_safe_url_redacts_query()
    test_apply_row_isolation_and_budget()
    test_apply_row_error_continues()
    print("\nALL HARNESS_ALL_TABS TESTS PASSED")


if __name__ == "__main__":
    main()
