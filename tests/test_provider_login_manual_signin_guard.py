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
