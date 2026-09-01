"""Offline tests for OmniRoute's full E2E acceptance coordinator."""
from __future__ import annotations

import omniroute_e2e_acceptance as e2e


def test_capability_summary_keeps_provider_model_modality_separate() -> None:
    summary = e2e.capability_summary({"providerModelCapabilityInventory": [
        {"provider": "alpha", "model": "alpha/chat", "modality": "chat"},
        {"provider": "alpha", "model": "alpha/video", "modality": "video_candidate"},
        {"provider": "beta", "model": "beta/chat", "modality": "chat"},
    ], "capabilityCounts": {"chat": 2, "video_candidate": 1}})
    assert summary["byProvider"] == {"alpha": {"chat": 1, "video_candidate": 1}, "beta": {"chat": 1}}
    assert summary["providerModelRows"] == 3


def test_release_never_certifies_preflight() -> None:
    report = {"directPlane": {"state": "STABLE_CATALOG"}, "gatewayAuth": {"state": "AUTH_GATE_PROVEN"}}
    assert e2e.release_state(report, False) == "PREFLIGHT_ONLY_NOT_CERTIFIABLE"


def test_private_loopback_gateway_without_tenant_map_is_not_auth_blocker() -> None:
    report = {
        "directPlane": {"state": "STABLE_CATALOG"},
        "gatewayAuth": {"state": "LOCAL_CONTRACT_OPEN_BY_DESIGN"},
    }
    assert e2e.release_state(report, True) == "MONETIZER_BLOCKED_NO_VERIFIED_OMNI_MODEL"


def test_unavailable_gateway_still_blocks_functional_e2e() -> None:
    report = {
        "directPlane": {"state": "STABLE_CATALOG"},
        "gatewayAuth": {"state": "GATEWAY_UNAVAILABLE"},
    }
    assert e2e.release_state(report, True) == "MONETIZER_BLOCKED_GATEWAY_UNAVAILABLE"


def test_release_requires_direct_stability_before_everything_else() -> None:
    report = {"directPlane": {"state": "UNSTABLE_OR_UNAVAILABLE"}, "gatewayAuth": {"state": "AUTH_GATE_PROVEN"}}
    assert e2e.release_state(report, True) == "MONETIZER_BLOCKED_OMNI_UNSTABLE"


def test_release_requires_real_consumer_job_results() -> None:
    report = {
        "directPlane": {"state": "STABLE_CATALOG"}, "gatewayAuth": {"state": "AUTH_GATE_PROVEN"},
        "providerSweep": {"counts": {"consumerLaw3": 1}},
        "routingContracts": {"gateway": {"state": "CONTRACT_PROVEN"}},
        "consumerApps": {"live": {"oioi": {"state": "OIOI_CREW_E2E_PROVEN"},
                                    "emergent": {"state": "EMERGENT_APP_E2E_NOT_PROVEN"}}},
    }
    assert e2e.release_state(report, True) == "MONETIZER_BLOCKED_EMERGENT_E2E"


def main() -> None:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} OMNI E2E ACCEPTANCE TESTS PASSED")


if __name__ == "__main__":
    main()
