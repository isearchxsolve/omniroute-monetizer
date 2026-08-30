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
