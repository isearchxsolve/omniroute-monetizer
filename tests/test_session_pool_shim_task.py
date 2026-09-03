from __future__ import annotations

import sys
from pathlib import Path


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

import session_pool_shim_task as task  # noqa: E402


def test_replace_request_is_atomic_and_one_shot(tmp_path) -> None:
    marker = tmp_path / "replace.request"
    task.request_replace(marker)

    assert marker.is_file()
    assert task.consume_replace_request(marker) is True
    assert task.consume_replace_request(marker) is False
    assert not marker.exists()
    assert not marker.with_suffix(".request.tmp").exists()


def test_force_replace_bypasses_healthy_shortcut(tmp_path, monkeypatch) -> None:
    events = []
    diag = tmp_path / "diag.log"
    primary = tmp_path / "primary.log"

    monkeypatch.setattr(task, "healthz", lambda _port: True)
    monkeypatch.setattr(
        task,
        "stop_owned_shims",
        lambda port, reason: events.append(("stop", port, reason)) or ([10, 11], []),
    )
    monkeypatch.setattr(
        task,
        "launch_shim",
        lambda port, log: events.append(("launch", port, log)) or 12,
    )
    monkeypatch.setattr(task, "wait_for_health", lambda _port: True)
    monkeypatch.setattr(
        task,
        "prune_owned_shims",
        lambda port, reason: events.append(("prune", port, reason)) or ([], []),
    )

    result = task.run_owner(
        8190, diag, primary, tmp_path, force_replace=True
    )

    assert result == 0
    assert events == [
        ("stop", 8190, "unhealthy"),
        ("launch", 8190, primary),
        ("prune", 8190, "healthy-orphan"),
    ]
    text = diag.read_text(encoding="utf-8")
    assert "REPLACE requested native-owner" in text
    assert "RECOVERED primary launcher_pid=12" in text
