"""Regression tests for zero-restart admission and quarantine hot reload."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

import session_pool_shim as shim


class FakePool:
    def __init__(self, secrets: Path) -> None:
        self.secrets = secrets
        self.calls = 0

    def rescan(self) -> dict:
        self.calls += 1
        return {"total": 0}


def _rewrite_with_new_mtime(path: Path, text: str, mtime_ns: int) -> None:
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_registry_edit_triggers_rescan_when_secrets_directory_is_unchanged(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    registry = tmp_path / "registry.json"
    quarantine = tmp_path / "quarantine.json"
    _rewrite_with_new_mtime(registry, '{"entries": []}\n', 10_000_000_000)
    _rewrite_with_new_mtime(quarantine, '{"hosts": {}}\n', 10_000_000_000)
    fake = FakePool(secrets)

    monkeypatch.setattr(shim, "pool", fake)
    monkeypatch.setattr(shim, "PURE_PYTHON_REGISTRY", registry)
    monkeypatch.setattr(shim, "POOL_QUARANTINE", quarantine)
    monkeypatch.setattr(shim, "_dir_sig", [None])

    shim._maybe_rescan()
    assert fake.calls == 1
    # Windows leaves the directory mtime unchanged for an in-place file edit.  The
    # registry signature must still force a second rescan.
    _rewrite_with_new_mtime(registry, '{"entries": [{"sessionFile": "new"}]}\n', 11_000_000_000)
    shim._maybe_rescan()
    assert fake.calls == 2


def test_quarantine_edit_triggers_rescan_without_a_restart(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    registry = tmp_path / "registry.json"
    quarantine = tmp_path / "quarantine.json"
    _rewrite_with_new_mtime(registry, '{"entries": []}\n', 20_000_000_000)
    _rewrite_with_new_mtime(quarantine, '{"hosts": {}}\n', 20_000_000_000)
    fake = FakePool(secrets)

    monkeypatch.setattr(shim, "pool", fake)
    monkeypatch.setattr(shim, "PURE_PYTHON_REGISTRY", registry)
    monkeypatch.setattr(shim, "POOL_QUARANTINE", quarantine)
    monkeypatch.setattr(shim, "_dir_sig", [None])

    shim._maybe_rescan()
    assert fake.calls == 1
    _rewrite_with_new_mtime(quarantine, '{"hosts": {"example.test": "adapter"}}\n', 21_000_000_000)
    shim._maybe_rescan()
    assert fake.calls == 2
