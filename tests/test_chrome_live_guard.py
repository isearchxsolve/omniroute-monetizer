"""Regression tests for stale Chrome DevToolsActivePort markers.

The marker is a safety hint, not proof that a browser is still running.  A crashed
Chrome can leave it behind; the guard must refuse only a port with a live loopback
listener.
"""

from __future__ import annotations

import socket


def _write_marker(root, port: int) -> None:
    (root / "DevToolsActivePort").write_text(f"{port}\n/devtools/browser/test\n", encoding="utf-8")


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def test_stale_devtools_marker_is_ignored(monkeypatch, tmp_path):
    """A marker left by a crashed browser must not permanently poison a seat port."""
    from scripts.automation import chrome_live_guard as guard

    _write_marker(tmp_path, _free_port())
    monkeypatch.setattr(guard, "LIVE_ROOT", tmp_path)

    assert guard.live_devtools_ports() == set()


def test_live_devtools_marker_requires_reachable_listener(monkeypatch, tmp_path):
    """A reachable listener remains protected even when the marker is otherwise identical."""
    from scripts.automation import chrome_live_guard as guard

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        port = int(listener.getsockname()[1])
        _write_marker(tmp_path, port)
        monkeypatch.setattr(guard, "LIVE_ROOT", tmp_path)

        assert guard.live_devtools_ports() == {port}
    finally:
        listener.close()
