from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from video_router import clips_from_individual_balances  # noqa: E402


def test_capacity_never_pools_credits_across_accounts() -> None:
    accounts = [SimpleNamespace(credits=value) for value in (0, 15, 0, 15)]

    assert clips_from_individual_balances(accounts, 20) == (0, 30)


def test_capacity_counts_multiple_clips_only_within_one_account() -> None:
    accounts = [SimpleNamespace(credits=value) for value in (45, 15, None)]

    assert clips_from_individual_balances(accounts, 20) == (2, 20)


def test_capacity_refuses_invalid_price_floor() -> None:
    accounts = [SimpleNamespace(credits=100)]

    assert clips_from_individual_balances(accounts, 0) == (0, 0)
