from __future__ import annotations

import base64
import json
import sys
from pathlib import Path


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
sys.path.insert(0, str(AUTOMATION))

import video_provider_probe as probe  # noqa: E402


def test_runnable_plan_excludes_unwired_and_image_to_video() -> None:
    registry = {
        "good": {
            "handlerImplemented": True,
            "baseUrl": "https://video.example",
            "models": [
                {"id": "t2v", "name": "T2V"},
                {"id": "i2v", "name": "I2V"},
            ],
        },
        "unwired": {
            "handlerImplemented": False,
            "models": [{"id": "t2v", "name": "not runnable"}],
        },
    }

    rows = probe.runnable_t2v_plan(registry)

    assert [row["qualified"] for row in rows] == ["good/t2v"]


def test_local_engines_are_opt_in_for_remote_fleet_plan() -> None:
    registry = {
        "local": {
            "handlerImplemented": True,
            "baseUrl": "http://127.0.0.1:8188",
            "models": [{"id": "t2v", "name": "local T2V"}],
        }
    }

    assert probe.runnable_t2v_plan(registry) == []
    assert [row["qualified"] for row in probe.runnable_t2v_plan(registry, include_local=True)] == [
        "local/t2v"
    ]


def test_inline_mp4_asset_is_verified_and_saved_without_network(tmp_path: Path) -> None:
    # A minimal ISO-BMFF signature is enough for the gate; ffprobe, when present,
    # may report that this synthetic fixture has no playable streams, which is
    # intentionally separate from the byte-level MP4 admission check.
    raw = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
    asset = {"kind": "base64", "value": base64.b64encode(raw).decode("ascii")}
    dest = tmp_path / "clip.mp4"

    result = probe.verify_video_asset(asset, dest)

    assert result["fetched"] is True
    assert result["is_mp4"] is True
    assert result["bytes"] == len(raw)
    assert dest.read_bytes() == raw


def test_progress_writer_is_atomic_and_publishes_only_mp4_rows(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    admission = tmp_path / "admission.json"
    monkeypatch.setattr(probe, "REPORT_PATH", report)
    monkeypatch.setattr(probe, "ADMISSION_PATH", admission)

    rows = [
        {
            "model": "good/t2v",
            "verification": {"is_mp4": True, "bytes": 123},
            "verifiedAt": "2026-09-01T00:00:00+00:00",
        },
        {"model": "bad/t2v", "verification": {"is_mp4": False}},
    ]
    probe._write_progress(
        plan=[{"qualified": "good/t2v"}, {"qualified": "bad/t2v"}],
        results=rows,
        started_at="2026-09-01T00:00:00+00:00",
    )

    saved = json.loads(report.read_text(encoding="utf-8"))
    ledger = json.loads(admission.read_text(encoding="utf-8"))
    assert saved["working"] == ["good/t2v"]
    assert [row["model"] for row in ledger["entries"]] == ["good/t2v"]
    assert list(tmp_path.glob("*.tmp")) == []


def test_local_backend_preflight_does_not_wait_for_gateway_timeout() -> None:
    assert probe.local_backend_unavailable("http://127.0.0.1:1") is True
    assert probe.local_backend_unavailable("https://example.invalid/video") is False
