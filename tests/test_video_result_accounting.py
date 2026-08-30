from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from video_result_accounting import credits_spent


def test_credits_spent_prefers_documented_result_key():
    assert credits_spent({"credits_spent": 12, "credits": 20}) == 12.0


def test_credits_spent_supports_flow_pool_client_compatibility_key():
    assert credits_spent({"credits": 20}) == 20.0


def test_credits_spent_is_honest_zero_for_missing_or_invalid_values():
    assert credits_spent({}) == 0.0
    assert credits_spent({"credits": "not-a-number"}) == 0.0
