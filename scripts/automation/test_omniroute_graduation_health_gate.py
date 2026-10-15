"""Additive tests for the gateway health gate and the chat-only scope filter.

These are NEW coverage for behaviour added 2026-10-15 (worklog #1944-#1945).
They do not modify ``test_omniroute_graduation.py`` - that file remains the
untouched contract judge for the master.

Basis for the gate (measured, not assumed): during the 2026-10-15 chat-only run
the local gateway stopped answering - ``/healthz`` silent for 20.4 s and
``/v1/models`` for 45.2 s while the shim stayed healthy at 0.96 s - and 73 of 151
rows then recorded TRANSPORT, losing eleven providers that had proven
DIRECT_LAW3_OK forty minutes earlier. A sweep must therefore wait a gateway
stall out and record the window in the run artifact.
"""
from __future__ import annotations

import omniroute_graduation as master


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Session:
    """Minimal stand-in for a requests.Session used by the health gate."""

    def __init__(self, statuses) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        nxt = self.statuses.pop(0) if self.statuses else 200
        if isinstance(nxt, Exception):
            raise nxt
        return _Response(nxt)


def test_gateway_health_reports_ok_and_latency() -> None:
    health = master.gateway_health(_Session([200]))
    assert health["ok"] is True
    assert health["status"] == 200
    assert isinstance(health["latencyMs"], int)


def test_gateway_health_never_raises_on_transport_error() -> None:
    health = master.gateway_health(_Session([TimeoutError("read timed out")]))
    assert health["ok"] is False
    assert health["status"] is None
    assert "TimeoutError" in health["error"]


def test_await_recovery_returns_immediately_when_gateway_is_healthy() -> None:
    gate = master.GatewayHealthGate(_Session([200]), max_wait_s=30, probe_every_s=1)
    result = gate.await_recovery("test", sleep=lambda _s: None)
    assert result["ok"] is True
    assert gate.stalls == []
    assert gate.checks == 1


def test_await_recovery_waits_out_a_stall_and_records_the_window() -> None:
    session = _Session([TimeoutError("stall"), TimeoutError("stall"), 200])
    gate = master.GatewayHealthGate(session, max_wait_s=60, probe_every_s=1)
    result = gate.await_recovery("transport:mistral/devstral-2512", sleep=lambda _s: None)
    assert result["ok"] is True
    assert len(gate.stalls) == 1
    window = gate.stalls[0]
    assert window["gaveUp"] is False
    assert window["gatewayAtStart"]["ok"] is False
    assert window["gatewayAtEnd"]["ok"] is True
    assert window["reason"].startswith("transport:mistral")
    assert session.calls == 3


def test_await_recovery_gives_up_at_the_bound_and_says_so() -> None:
    gate = master.GatewayHealthGate(_Session([TimeoutError("stall")] * 10), max_wait_s=3, probe_every_s=1)
    result = gate.await_recovery("transport:vertex/x", sleep=lambda _s: None)
    assert result["ok"] is False
    assert result["gaveUp"] is True
    assert len(gate.stalls) == 1
    assert gate.stalls[0]["gaveUp"] is True
    assert gate.stalls[0]["gatewayAtEnd"] is None


def test_chat_only_scope_drops_video_and_image_leftovers() -> None:
    catalog = [
        {"id": "mistral/devstral-2512", "owned_by": "mistral"},
        {"id": "ainative/alibaba-wan-22-i2v-720p", "owned_by": "ainative"},
        {"id": "comfyui/animatediff", "owned_by": "comfyui"},
        {"id": "aihorde/Realistic Vision", "owned_by": "aihorde"},
        {"id": "jina-ai/jina-clip-v2", "owned_by": "jina-ai"},
    ]
    routes = master.plan_from_catalog(catalog)
    assert [(r["provider"], r["model"]) for r in routes] == [("mistral", "mistral/devstral-2512")]


def test_chat_only_scope_keeps_multimodal_chat_models() -> None:
    catalog = [
        {"id": "nvidia/meta/llama-3.2-11b-vision-instruct", "owned_by": "nvidia"},
        {"id": "deepinfra/Qwen/Qwen3-VL-235B-A22B-Instruct", "owned_by": "deepinfra"},
    ]
    routes = master.plan_from_catalog(catalog)
    assert len(routes) == 2


def test_excluded_rows_stay_in_the_capability_inventory() -> None:
    catalog = [
        {"id": "mistral/devstral-2512", "owned_by": "mistral"},
        {"id": "cohere/embed-english-light-v3.0", "owned_by": "cohere"},
    ]
    inventory = {row["model"] for row in master.capability_inventory(catalog)}
    assert inventory == {"mistral/devstral-2512", "cohere/embed-english-light-v3.0"}


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} HEALTH-GATE / CHAT-SCOPE TESTS PASSED")


if __name__ == "__main__":
    main()
