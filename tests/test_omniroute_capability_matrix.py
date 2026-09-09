from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
sys.path.insert(0, str(AUTOMATION))

from omniroute_capability_matrix import PATHS, _shape  # noqa: E402


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/ok":
            body = b'{"status":"ok"}'
            self.send_response(200)
        else:
            body = b'{"status":"bad"}'
            self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_supervisor_has_application_paths_for_unowned_services() -> None:
    from omni_supervisor import services

    configured = {svc.key: svc.health for svc in services()}
    assert configured["omniroute"] == "/api/health"
    assert configured["video_router"] == "/healthz"
    assert configured["session_pool_shim"] == "/healthz"


def test_management_client_canonicalizes_loopback_and_disables_proxy_inheritance() -> None:
    from omniroute_api import OmniRouteAPI

    api = OmniRouteAPI(base_url="http://localhost:20128/v1", password="test-only")
    assert api.base == "http://127.0.0.1:20128"
    assert api.api == "http://127.0.0.1:20128/api"
    assert api.session.trust_env is False


def test_consumer_catalog_audit_uses_tenant_auth_without_echoing_key(tmp_path, monkeypatch) -> None:
    import audit_merged_healthy_capacity as audit

    tenant_map = tmp_path / "tenant_map.json"
    tenant_map.write_text(json.dumps({"sk-test-tenant": "opaque"}), encoding="utf-8")
    monkeypatch.setattr(audit, "TENANT_MAP", tenant_map)

    assert audit.consumer_auth_headers() == {"Authorization": "Bearer sk-test-tenant"}


def test_keepalive_expiry_parser_handles_utc_and_rejects_bad_metadata() -> None:
    from oauth_keepalive import parse_expiry

    parsed = parse_expiry("2026-09-09T09:43:15.000Z")
    assert parsed is not None and parsed.utcoffset().total_seconds() == 0
    assert parse_expiry("not-a-timestamp") is None
    assert parse_expiry(None) is None


def test_universal_replay_extracts_duckchat_message_sse_frames() -> None:
    from universal_replay import UniversalSessionClient

    client = object.__new__(UniversalSessionClient)
    client._last_prompt = "Reply with only the number: 41 + 17"
    body = 'data: {"message":"5"}\n\ndata: {"message":"8"}\n\ndata: [DONE]\n'
    text, error = client._extract_response(body)
    assert text == "58"
    assert error is None


def test_v0_pipeline_selects_and_substitutes_real_chat_submit_leg() -> None:
    from universal_replay import _leg2_for

    raw = {"recorded_exchanges": [
        {"url": "https://v0.app/chat/api/send", "request_body": '{"chat_id":"slug-id"}'},
        {"url": "https://v0.app/chat/api/send", "request_body": '{"promptText":"Reply exactly one word: Omni."}'},
        {"url": "https://v0.app/chat/api/chat", "request_body":
         '{"messageId":"old","chatId":"bare-id","messageContent":{"parts":[{"content":"Reply exactly one word: Omni."}]}}'},
    ]}

    leg = _leg2_for("v0.app", raw, "Reply with only the number: 41 + 17")
    assert leg is not None
    assert leg["url"].endswith("/chat/api/chat")
    assert '"chatId":"bare-id"' in leg["request_body"]
    assert "Reply with only the number: 41 + 17" in leg["request_body"]


def test_v0_followup_replays_submit_then_polls_new_assistant(monkeypatch) -> None:
    import multistep_replay as ms

    posted = {}

    class _SubmitResponse:
        status_code = 200
        text = "ok"

    class _PollResponse:
        status_code = 200

        def __init__(self):
            self.text = json.dumps({"value": {"newMessages": [{
                "role": "assistant",
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "content": ["text", {}, "58"],
            }]}})

    def fake_post(url, headers=None, data=None, timeout=None):
        posted["url"] = url
        posted["body"] = json.loads(data.decode("utf-8"))
        return _SubmitResponse()

    monkeypatch.setattr(ms, "_HAVE_CURL_CFFI", False)
    monkeypatch.setattr(ms.requests, "post", fake_post)
    monkeypatch.setattr(ms, "_stream_get", lambda *args, **kwargs: _PollResponse())

    leg = {
        "url": "https://v0.app/chat/api/chat",
        "request_headers": {"content-type": "application/json"},
        "request_body": json.dumps({
            "messageId": "old-message",
            "chatId": "bare-id",
            "messageContent": {"parts": [{"type": "mdx", "content": "Reply exactly one word: Omni."}]},
        }),
    }
    answer, error = ms.v0_followup(
        "ok", {"User-Agent": "test"}, "", timeout=1,
        chat_id="bare-id", started_ms=int(time.time() * 1000) - 1000, leg2=leg)
    assert error is None
    assert answer == "58"
    assert posted["url"].endswith("/chat/api/chat")
    assert posted["body"]["messageId"] != "old-message"
    assert posted["body"]["chatId"] == "bare-id"
    assert posted["body"]["messageContent"]["parts"][0]["content"] == "Reply exactly one word: Omni."


def test_v0_followup_error_keeps_final_leg_http_status() -> None:
    from universal_replay import _followup_http_status

    assert _followup_http_status("V0_CHAT_SUBMIT_401: 2", 200) == 401
    assert _followup_http_status("V0_POLL_429: busy", 200) == 429
    assert _followup_http_status("V0_NO_NEW_MESSAGE", 200) == 200


def test_pipeline_marker_does_not_hide_explicit_credit_wall() -> None:
    from replay_check import apply_pipeline_override

    verdict, detail = apply_pipeline_override(
        "WALL", "credit wall", 'data: {"type":"project_start"}')
    assert verdict == "WALL"
    assert detail == "credit wall"

    verdict, detail = apply_pipeline_override(
        "NO_ANSWER", "no answer", 'data: {"type":"project_start"}')
    assert verdict == "PIPELINE"
    assert "multi-step build target" in detail


def test_v0_missing_chat_id_is_capture_error_not_single_use() -> None:
    from replay_check import classify

    verdict, detail = classify("V0_NO_CHAT_ID", 200, None, "58")
    assert verdict == "BAD_FILE"
    assert "conversation id" in detail


def test_paths_are_read_only_capability_surface() -> None:
    assert set(PATHS) == {
        "health",
        "models",
        "combos",
        "compression_status",
        "relay_proxies",
    }
    assert all(path.startswith("/") for path in PATHS.values())


def test_shape_records_safe_object_metadata_only() -> None:
    shaped = _shape(json.dumps({"data": [{"id": "m1"}], "status": "ok"}).encode())
    assert shaped["json"] is True
    assert shaped["type"] == "object"
    assert shaped["dataType"] == "list"
    assert shaped["dataCount"] == 1
    assert "keys" in shaped


def test_shape_handles_non_json_without_body() -> None:
    shaped = _shape(b"not-json")
    assert shaped == {"bytes": 8, "json": False}


def test_capability_summary_separates_auth_from_transport_failure() -> None:
    from omniroute_capability_matrix import summarize

    summary = summarize([
        {"ok": True, "status": 200},
        {"ok": False, "status": 401, "error": "http_error"},
        {"ok": False, "status": 404, "error": "http_error"},
        {"ok": False, "status": None, "error": "TimeoutError"},
    ])
    assert summary == {"ok2xx": 1, "auth4xx": 1, "other4xx": 1, "server5xx": 0, "timeouts": 1}


def test_combo_catalog_extract_rows_is_shape_safe() -> None:
    from omniroute_combo_catalog_audit import extract_rows

    assert extract_rows({"combos": [{"name": "frontier"}]}, "combos") == [{"name": "frontier"}]
    assert extract_rows({"data": []}, "combos") == []
    assert extract_rows([], "combos") == []


def test_combo_recommendation_provider_and_scoring_are_deterministic() -> None:
    from omniroute_combo_recommendations import provider_key, score

    assert provider_key("openrouter/qwen/qwen3") == "openrouter"
    assert score("mistral/codestral-2508", "auto/pro-coding") > score("mistral/large", "auto/pro-coding")


def test_chat_probe_extracts_assistant_text_from_sse() -> None:
    from omniroute_api import extract_chat_content

    sse = 'data: {"choices":[{"delta":{"content":"O"}}]}\n\ndata: {"choices":[{"delta":{"content":"K"}}]}\n\ndata: [DONE]\n'
    assert extract_chat_content({"raw": "ignored"}, sse) == "OK"


def test_chat_probe_extracts_assistant_text_from_json() -> None:
    from omniroute_api import extract_chat_content

    body = {"choices": [{"message": {"content": "OK"}}]}
    assert extract_chat_content(body) == "OK"


def test_combo_backup_uses_dedicated_state_directory() -> None:
    import backup_omniroute_combos

    assert backup_omniroute_combos.ROOT.name == "omniroute-monetizer"


def test_video_capability_summary_redacts_accounts() -> None:
    from video_capability_audit import summarize

    report = summarize(
        {"ok": True, "dry_run": False, "authenticated": True, "providers": ["flow"],
         "accounts": [{"email": "private@example.com", "ready": True}], "jobs": {"total": 2}},
        {"data": [{"id": "fast", "provider": "flow", "proven": True, "est_cost": 20}]},
    )
    assert report["accountsReady"] == 1
    assert "accounts" not in report
    assert report["models"][0]["id"] == "fast"


def test_contract_helpers_classify_sse_and_tool_calls() -> None:
    from omniroute_contract_probe import sse_contract, tool_contract

    assert sse_contract('data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n') == {
        "hasDataFrame": True, "hasDone": True, "hasContent": True}
    assert tool_contract({"choices": [{"message": {"tool_calls": [{"id": "call_1"}]}}]})["hasToolCall"] is True


def test_acceptance_secret_scanner_keeps_real_keys_and_ignores_examples() -> None:
    from acceptance_tests import is_documentation_placeholder

    assert is_documentation_placeholder('API-Key: YDC_API_KEY') is True
    assert is_documentation_placeholder('api_key": "tenant_name') is True
    assert is_documentation_placeholder("sk-abcDef1234567890xyz") is False


def test_supervisor_application_probe_distinguishes_http_success_and_failure() -> None:
    from omni_supervisor import http_health

    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        ok, payload = http_health(port, "/ok")
        assert ok is True
        assert payload == {"status": "ok"}
        failed, reason = http_health(port, "/bad")
        assert failed is False
        assert reason == "HTTP 503"
    finally:
        server.shutdown()
        server.server_close()


def test_supervisor_report_declares_schema_and_writer_identity() -> None:
    from omni_supervisor import one_pass, services

    report = one_pass(services()[:0], fix=False)
    assert report["schemaVersion"] == 2
    assert isinstance(report["writerPid"], int)
    assert report["writerPython"]
    assert report["allApplicationHealthy"] is True


def test_supervisor_defines_process_owned_instance_lock() -> None:
    import omni_supervisor

    assert omni_supervisor.INSTANCE_LOCK_FILE.name == "supervisor.lock"
    assert callable(omni_supervisor.acquire_instance_lock)
    assert omni_supervisor.AUTHORITATIVE_STATUS_FILE.name == "supervisor_status_v2.json"
    assert omni_supervisor.MEMORY_WARNING_BYTES == 2 * 1024 * 1024 * 1024
