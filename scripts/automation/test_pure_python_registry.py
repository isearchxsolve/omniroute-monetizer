"""Offline contract checks for exact-file pure-Python admission.  No Chrome/network."""
from __future__ import annotations

import json
import pathlib
import tempfile

from pure_python_registry import (admission_problem, admit, admitted_chat_session_keys, admitted_video_session_keys,
                                  load_registry, pure_python_adapter, transport_for, write_registry)


def chat_http() -> dict:
    return {"host": "example.ai", "modality": "chat", "recorded_exchange": {"request_body": "x"}}


def test_http_and_websocket_select_python_clients() -> None:
    assert transport_for(chat_http()) == "http"
    assert pure_python_adapter(chat_http()) == "universal_replay.UniversalSessionClient"
    ws = {"host": "ws.example.ai", "modality": "chat", "transport": "websocket", "recorded_ws": {"url": "wss://ws.example.ai"}}
    assert transport_for(ws) == "websocket"
    assert pure_python_adapter(ws) == "ws_replay.WebSocketSessionClient"
    assert admission_problem(ws) is None


def test_reject_chrome_and_empty_artifacts() -> None:
    assert "Chrome-backed" in str(admission_problem({"host": "x", "chrome": True, "recorded_exchange": {}}))
    assert "no registered" in str(admission_problem({"host": "x", "modality": "chat"}))


def test_public_ltx_space_is_a_registered_python_api_kind() -> None:
    raw = {
        "host": "lightricks-ltx-video-distilled.hf.space",
        "modality": "video",
        "api": {"kind": "hf_ltx_space"},
    }
    assert pure_python_adapter(raw) == "api:hf_ltx_space"
    assert admission_problem(raw) is None


def test_exact_file_admission_is_atomic_and_not_host_scoped() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "registry.json"
        reg = load_registry(path)
        admit(reg, session_file="session_same_host_a.json", host="same.host", modality="chat",
              adapter="universal_replay.UniversalSessionClient", verification={"verdict": "REPLAY_OK"})
        write_registry(reg, path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["entries"][0]["sessionFile"] == "session_same_host_a.json"
        assert admitted_chat_session_keys(path) == {"session_same_host_a"}
        # Another account on the same host is not admitted by host coincidence.
        assert "session_same_host_b" not in admitted_chat_session_keys(path)


def test_video_admission_is_also_exact_file_scoped() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "registry.json"
        reg = load_registry(path)
        admit(reg, session_file="session_labs_google_flow_a.json", host="labs.google", modality="video",
              adapter="video_universal_replay.VideoUniversalSessionClient",
              verification={"resultUrlObserved": True})
        write_registry(reg, path)
        assert admitted_video_session_keys(path) == {"session_labs_google_flow_a"}
        assert "session_labs_google_flow_b" not in admitted_video_session_keys(path)


def test_session_pool_accepts_exact_admission_without_host_gate() -> None:
    """Regression: a verified account must not promote its sibling by host name."""
    import session_pool
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        secrets = root / "secrets"
        secrets.mkdir()
        seat = secrets / "session_same_host_a.json"
        seat.write_text(json.dumps({
            "host": "same.host", "modality": "chat", "runtime": "replay",
            "recorded_exchange": {"url": "https://same.host/api", "method": "POST",
                                  "request_headers": {}, "request_body": "needle"},
        }), encoding="utf-8")
        registry_path = root / "registry.json"
        reg = load_registry(registry_path)
        admit(reg, session_file=seat.name, host="same.host", modality="chat",
              adapter="universal_replay.UniversalSessionClient", verification={"verdict": "REPLAY_OK"})
        write_registry(reg, registry_path)
        old_registry, old_gate = session_pool.PURE_PYTHON_REGISTRY, session_pool.REPLAY_GATE
        try:
            session_pool.PURE_PYTHON_REGISTRY = registry_path
            session_pool.REPLAY_GATE = root / "missing-replay-gate.json"
            pool = session_pool.SessionPool(secrets=secrets)
            assert [s.key for s in pool.live(modality="chat")] == ["session_same_host_a"]
        finally:
            session_pool.PURE_PYTHON_REGISTRY = old_registry
            session_pool.REPLAY_GATE = old_gate


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} PURE-PYTHON REGISTRY TESTS PASSED")


if __name__ == "__main__":
    main()
