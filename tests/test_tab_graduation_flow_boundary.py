"""Safety boundary for distinguishing Flow video tabs from Gemini chat tabs."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from tab_graduation_sweep import classify_tab  # noqa: E402


def test_flow_project_tab_is_never_offered_to_chat_capture():
    """A broad google.com readiness record must not alias Flow to Gemini."""
    row = classify_tab(
        {"id": "flow-target", "url": "https://flow.google.com/project/abc-123"},
        {"google.com": {"site": "Google Gemini Web", "readiness": "signed_in_probable"}},
        {},
        {},
    )

    assert row["knownSite"] == "Google Flow (flow.google.com)"
    assert row["classification"] == "VIDEO_SEPARATE_GRADUATION"
    assert row["nextAction"] == "video_contract_and_spend_gate"
