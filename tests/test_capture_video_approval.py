"""Unit tests for the spend-gated Flow approval handoff."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

import capture_video_job_cdp as capture  # noqa: E402


class FakeCDP:
    def __init__(self, probes):
        self.probes = iter(probes)
        self.calls = []

    def evaluate(self, _script, timeout=20):
        return next(self.probes)

    def call(self, method, params=None, timeout=15):
        self.calls.append((method, params, timeout))
        return {}


def test_clicks_only_the_one_time_approve_control():
    c = FakeCDP([{"pending": True, "ok": True, "x": 100, "y": 200}])
    row = {}

    assert capture._approve_pending_video(c, row) is True
    assert row["approval"] == "approve_clicked"
    assert [call[0] for call in c.calls] == [
        "Input.dispatchMouseEvent",
        "Input.dispatchMouseEvent",
        "Input.dispatchMouseEvent",
    ]
    assert all(call[1]["x"] == 100 and call[1]["y"] == 200 for call in c.calls)


def test_does_not_click_when_card_has_no_active_control():
    c = FakeCDP([{"pending": True, "ok": False}, {"pending": False}])
    row = {}

    assert capture._approve_pending_video(c, row) is False
    assert row["approval"] == "not_required_or_already_approved"
    assert c.calls == []


def test_selector_is_exact_and_excludes_always_approve():
    source = capture.JS_APPROVAL_PROBE
    assert "label === 'Approve'" in source
    assert "Always approve" not in source
    assert "el.disabled" in source
    assert "aria-disabled" in source
