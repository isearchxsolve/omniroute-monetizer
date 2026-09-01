"""Offline tests for the non-blocking Omni catalog bridge."""
from __future__ import annotations

import time
from unittest.mock import patch

from session_pool_shim import OmniRouteBridge, SHIM_HEALTH_VERSION, shim_health_payload


class FakeResponse:
    ok = True

    def json(self):
        return {"data": [{"id": "omni/test", "owned_by": "test"}]}


def test_models_returns_cached_snapshot_while_refresh_runs() -> None:
    bridge = OmniRouteBridge("http://127.0.0.1:20128")
    bridge._models = [{"id": "omni/cached"}]
    bridge._models_at = 0.0
    bridge._refresh_at = 0.0
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        time.sleep(0.05)
        return FakeResponse()

    with patch("session_pool_shim.requests.Session.get", fake_get):
        started = time.perf_counter()
        assert bridge.models() == [{"id": "omni/cached"}]
        # Thread startup is platform-dependent; the important property is that
        # the 50 ms fake upstream wait is not on this request path.
        assert time.perf_counter() - started < 0.2
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not bridge._models_at:
            time.sleep(0.005)

    assert len(calls) == 1
    assert bridge.models() == [{"id": "omni/test", "owned_by": "test"}]


def test_stale_refresh_is_coalesced() -> None:
    bridge = OmniRouteBridge("http://127.0.0.1:20128")
    bridge._models = [{"id": "omni/cached"}]
    bridge._models_at = 0.0
    bridge._refresh_at = 0.0
    def slow_get(*args, **kwargs):
        time.sleep(0.05)
        return FakeResponse()

    with patch("session_pool_shim.requests.Session.get", side_effect=slow_get) as get:
        assert bridge.models() == [{"id": "omni/cached"}]
        assert bridge.models() == [{"id": "omni/cached"}]
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and get.call_count < 1:
            time.sleep(0.005)
        time.sleep(0.02)
        assert get.call_count == 1


def test_health_payload_is_constant_local_liveness_metadata() -> None:
    payload = shim_health_payload()
    assert payload["ok"] is True
    assert payload["service"] == "session-pool-shim"
    assert payload["version"] == SHIM_HEALTH_VERSION
    assert isinstance(payload["pid"], int)
    assert "upstream" not in payload
