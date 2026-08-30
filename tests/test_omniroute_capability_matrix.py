from __future__ import annotations

import json
import sys
import threading
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
    assert configured["omniroute"] == "/v1/models"
    assert configured["video_router"] == "/healthz"
    assert configured["session_pool_shim"] == "/v1/models"


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
