from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from video_provider_flow import (  # noqa: E402
    FLOW_MATCH,
    FLOW_URL,
    FlowProvider,
    _flow_match,
    _is_flow_tab,
)
from video_provider import Account  # noqa: E402
from flow_ui_client import FlowUiClient  # noqa: E402


def test_migrated_flow_project_tab_is_detected() -> None:
    target = {"type": "page", "url": "https://flow.google.com/project/abc", "title": ""}
    assert _is_flow_tab(target)


def test_legacy_flow_project_tab_remains_compatible() -> None:
    target = {
        "type": "page",
        "url": "https://labs.google/fx/tools/flow/project/abc",
        "title": "",
    }
    assert _is_flow_tab(target)


def test_non_flow_page_is_not_selected() -> None:
    assert not _is_flow_tab({"type": "page", "url": "https://example.test/tools/flow"})


def test_flow_match_returns_concrete_migrated_target_url() -> None:
    target = {"type": "page", "url": "https://flow.google.com/project/abc", "title": ""}
    with patch("video_provider_flow.list_targets", return_value=[target]):
        assert _flow_match(9223) == target["url"]


def test_provider_defaults_to_migrated_selector() -> None:
    provider = FlowProvider()
    assert provider.tab_match == FLOW_MATCH
    assert provider.default_url == FLOW_URL


def test_probe_uses_migrated_ui_balance_instead_of_retired_json_endpoint() -> None:
    target = {
        "type": "page",
        "url": "https://flow.google.com/project/abc12345-de67-4890-ab12-abcdef123456",
        "title": "",
    }
    account = Account("flow", 9223, label="niloy-1", url=target["url"])
    provider = FlowProvider()
    with patch("video_provider_flow.list_targets", return_value=[target]), \
         patch("video_provider_flow.vp.assert_cdp_safe"), \
         patch.object(FlowUiClient, "capacity", return_value={"creditsRemaining": 120}):
        provider.probe(account)
    assert account.ready is True
    assert account.credits == 120
    assert account.fault is None
    assert account.project_id == "abc12345-de67-4890-ab12-abcdef123456"
