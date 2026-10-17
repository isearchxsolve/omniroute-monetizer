"""Additive coverage for strict Digen credit parsing (2026-10-17).

Measured live schema: ``GET https://api.digen.ai/v1/credit/remain`` returns
``{"errCode":0,"data":{"remained":0,"premiumRemained":0}}``. The provider used to
read ``data.remain`` and default a missing field to ``0``, which made a schema
change look exactly like a genuine zero balance - fatal for a spend gate.

New coverage only; no existing test is modified.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import video_provider_digen as module  # noqa: E402
from video_provider_digen import DigenProvider  # noqa: E402


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _provider(monkeypatch, payload, status_code: int = 200) -> DigenProvider:
    provider = object.__new__(DigenProvider)
    provider._headers = {}
    provider._loaded = True
    provider._load_session = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(module.requests, "get",
                        lambda *_args, **_kwargs: _FakeResponse(payload, status_code))
    return provider


def test_balance_sums_the_two_live_credit_pools(monkeypatch) -> None:
    provider = _provider(monkeypatch, {"errCode": 0, "data": {"remained": 270, "premiumRemained": 30}})
    assert provider._get_balance() == 300


def test_balance_accepts_a_single_pool(monkeypatch) -> None:
    provider = _provider(monkeypatch, {"errCode": 0, "data": {"premiumRemained": 12}})
    assert provider._get_balance() == 12


def test_a_verified_zero_is_reported_as_zero(monkeypatch) -> None:
    """A present field equal to 0 is a real answer, not a schema failure."""
    provider = _provider(monkeypatch, {"errCode": 0, "data": {"remained": 0, "premiumRemained": 0}})
    assert provider._get_balance() == 0


def test_the_old_remain_field_is_a_schema_error_not_a_zero(monkeypatch) -> None:
    provider = _provider(monkeypatch, {"errCode": 0, "data": {"remain": 500}})
    with pytest.raises(RuntimeError) as excinfo:
        provider._get_balance()
    message = str(excinfo.value)
    assert "schema mismatch" in message
    assert "remained" in message


def test_a_missing_data_object_is_a_schema_error(monkeypatch) -> None:
    provider = _provider(monkeypatch, {"errCode": 0})
    with pytest.raises(RuntimeError) as excinfo:
        provider._get_balance()
    assert "no data object" in str(excinfo.value)


def test_a_non_zero_err_code_still_fails_loudly(monkeypatch) -> None:
    provider = _provider(monkeypatch, {"errCode": 4002, "data": {"remained": 10}})
    with pytest.raises(RuntimeError) as excinfo:
        provider._get_balance()
    assert "credit/remain failed" in str(excinfo.value)
