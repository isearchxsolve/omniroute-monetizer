from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

import provider_login_helper as helper


def test_manual_signin_refuses_when_the_dedicated_profile_is_already_managed(
    monkeypatch, tmp_path, capsys
):
    """A second Chrome launch would be forwarded into the managed seat instance."""

    profile = tmp_path / "providers"
    launched = []

    monkeypatch.setattr(helper, "safe_profile_dir", lambda _tag: profile)
    monkeypatch.setattr(helper, "assert_safe", lambda path, who: path)
    monkeypatch.setattr(helper, "_chrome_using_profile", lambda _path: 1)
    monkeypatch.setattr(helper, "_find_chrome", lambda: launched.append(True))

    assert helper.run_manual_signin() == 4
    assert launched == []
    assert "already open by a managed Chrome seat" in capsys.readouterr().out


def test_manual_signin_refuses_when_profile_occupancy_cannot_be_verified(
    monkeypatch, tmp_path, capsys
):
    profile = tmp_path / "providers"
    launched = []

    monkeypatch.setattr(helper, "safe_profile_dir", lambda _tag: profile)
    monkeypatch.setattr(helper, "assert_safe", lambda path, who: path)
    monkeypatch.setattr(helper, "_chrome_using_profile", lambda _path: -1)
    monkeypatch.setattr(helper, "_find_chrome", lambda: launched.append(True))

    assert helper.run_manual_signin() == 4
    assert launched == []
    assert "Could not verify" in capsys.readouterr().out


def test_sso_profile_uses_a_distinct_human_only_profile_tag(monkeypatch, tmp_path):
    seen = []

    def profile(tag):
        seen.append(tag)
        return tmp_path / tag

    monkeypatch.setattr(helper, "safe_profile_dir", profile)
    monkeypatch.setattr(helper, "assert_safe", lambda path, who: path)
    monkeypatch.setattr(helper, "_chrome_using_profile", lambda _path: 1)

    assert helper.run_manual_signin(profile_tag=helper.SSO_PROFILE_TAG) == 4
    assert seen == ["providers_sso"]


def test_manual_signin_sso_switch_selects_the_distinct_profile(monkeypatch):
    selected = []

    monkeypatch.setattr(helper, "run_manual_signin", lambda profile_tag: selected.append(profile_tag) or 0)

    assert helper.main(["--manual-signin", "--sso-profile"]) == 0
    assert selected == [helper.SSO_PROFILE_TAG]


def test_interactive_sso_switch_selects_the_distinct_profile(monkeypatch):
    selected = []

    monkeypatch.setattr(
        helper,
        "run_interactive",
        lambda only, do_google, profile_tag: selected.append((only, do_google, profile_tag)) or 0,
    )

    assert helper.main(["--only", "kie", "--sso-profile"]) == 0
    assert selected == [(["kie"], False, helper.SSO_PROFILE_TAG)]


def test_open_browser_refuses_an_occupied_profile_before_playwright_launch(monkeypatch, tmp_path):
    class UnexpectedBrowser:
        def launch_persistent_context(self, **_kwargs):
            raise AssertionError("an occupied profile must never be launched")

    class FakePlaywright:
        chromium = UnexpectedBrowser()

    profile = tmp_path / "providers_sso"
    monkeypatch.setattr(helper, "safe_profile_dir", lambda _tag: profile)
    monkeypatch.setattr(helper, "assert_safe", lambda path, who: path)
    monkeypatch.setattr(helper, "_chrome_using_profile", lambda _path: 1)

    try:
        helper._open_browser(FakePlaywright(), profile_tag=helper.SSO_PROFILE_TAG)
    except helper.ProfileInUse as exc:
        assert "already open" in str(exc)
    else:
        raise AssertionError("occupied profiles must fail closed")
