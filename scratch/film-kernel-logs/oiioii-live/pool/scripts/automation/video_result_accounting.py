"""Normalise provider video-result accounting for the durable consumer ledger."""
from __future__ import annotations

from typing import Any, Mapping


def credits_spent(result: Mapping[str, Any]) -> float:
    """Read the documented key first, then the pool-client compatibility key.

    ``FlowApiClient`` returns ``credits`` while older replay clients return
    ``credits_spent``. The durable ``:8190`` job receipt must preserve either result
    accurately instead of reporting a completed, charged render as zero cost.
    """
    value = result.get("credits_spent")
    if value is None:
        value = result.get("credits")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
