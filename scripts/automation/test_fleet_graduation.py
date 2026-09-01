"""Offline command-contract checks for the master graduation coordinator."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import pathlib
import tempfile
import sys

import fleet_graduation as fleet


def test_sso_recovery_uses_one_exact_host() -> None:
    with patch.object(fleet.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
        fleet.recover_sso(9223, "chat.qwen.ai", 91.0)
    command = run.call_args.args[0]
    assert "--host-exact" in command
    assert command[command.index("--host-exact") + 1] == "chat.qwen.ai"
    assert "--host" not in command
    assert command[command.index("--port") + 1] == "9223"


def test_sso_recovery_refuses_urls_and_paths() -> None:
    for bad in ("https://chat.qwen.ai", "chat.qwen.ai/login", "chat.qwen.ai?x=1", ""):
        try:
            fleet.recover_sso(9223, bad, 30.0)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"did not reject {bad!r}")


def test_e2e_plan_covers_every_declared_profile_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        accounts = pathlib.Path(td) / "video_accounts.json"
        accounts.write_text(json.dumps({"accounts": [
            {"profile": "providers", "port": 9222, "label": "a", "provider": "flow", "enabled": True},
            {"profile": "providers", "port": 9222, "label": "b", "provider": "rtst", "enabled": True},
            {"profile": "niloy", "port": 9223, "label": "c", "provider": "flow", "enabled": True},
            {"profile": "seat2", "port": 9224, "label": "d", "provider": "flow", "enabled": True},
            {"profile": "seat3", "port": 9225, "label": "e", "provider": "flow", "enabled": True},
        ]}), encoding="utf-8")
        with patch.object(fleet, "SEAT_ACCOUNTS", accounts):
            plan = fleet.e2e_plan()
    assert [(row["profile"], row["port"]) for row in plan["fleet"]] == [
        ("providers", 9222), ("niloy", 9223), ("seat2", 9224), ("seat3", 9225)]
    assert plan["fleet"][0]["labels"] == ["a", "b"]


def test_complete_master_requires_explicit_video_spend_confirmation() -> None:
    with patch.object(sys, "argv", ["fleet_graduation.py", "--apply", "--e2e"]):
        try:
            fleet.main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("complete master accepted an unconfirmed video spend")


def test_complete_master_orders_chat_consumer_then_video() -> None:
    calls: list[str] = []
    with patch.object(fleet, "e2e_chat_apply", side_effect=lambda *a: calls.append("chat")), \
         patch.object(fleet, "e2e_chat_consumer_proofs", side_effect=lambda: calls.append("chat-consumer")), \
         patch.object(fleet, "e2e_video_apply", side_effect=lambda *a: calls.append("video")):
        fleet.e2e_apply(11.0, 12.0, 0, 13.0)
    assert calls == ["chat", "chat-consumer", "video"]


def test_video_only_continuation_does_not_rerun_chat() -> None:
    calls: list[str] = []
    original = os.environ.get("OMNI_VIDEO_CONFIRM_SPEND")
    with patch.object(fleet, "e2e_video_apply", side_effect=lambda *a: calls.append("video")), \
         patch.object(fleet, "e2e_chat_apply", side_effect=lambda *a: calls.append("chat")), \
         patch.object(fleet, "e2e_chat_consumer_proofs", side_effect=lambda: calls.append("chat-consumer")):
        fleet.e2e_video_only_apply(13.0, 11.0)
    assert calls == ["video"]
    assert os.environ.get("OMNI_VIDEO_CONFIRM_SPEND") == original


def test_video_only_master_requires_explicit_spend_confirmation() -> None:
    with patch.object(sys, "argv", ["fleet_graduation.py", "--apply", "--e2e-video"]):
        try:
            fleet.main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("video-only master accepted an unconfirmed video spend")


def test_video_lane_resumes_without_repeating_terminal_seat() -> None:
    with tempfile.TemporaryDirectory() as td:
        run_path = pathlib.Path(td) / "video_run.json"
        run_path.write_text(json.dumps({
            "generatedAt": "earlier", "seats": [
                {"label": "digen-01", "host": "digen.ai", "state": "NOT_ADMITTED"}
            ], "consumerProofs": []
        }), encoding="utf-8")
        accounts = [
            {"label": "digen-01", "host": "digen.ai", "profile": "providers", "port": 9222},
            {"label": "flow-seat2", "host": "labs.google", "profile": "seat2", "port": 9224},
        ]
        with patch.object(fleet, "E2E_VIDEO_RUN", run_path), \
             patch.object(fleet, "declared_video_accounts", return_value=accounts), \
             patch.object(fleet, "capture_and_graduate_video", return_value={
                 "label": "flow-seat2", "host": "labs.google", "state": "ADMITTED_TO_8190_PURE_PYTHON"
             }) as capture, \
             patch.object(fleet, "consumer_video_probe", return_value={
                 "host": "labs.google", "state": "CONSUMER_E2E_PROVEN", "resultUrlObserved": True
             }), \
             patch.object(fleet.time, "sleep"):
            fleet.e2e_video_apply(13.0, 11.0)
        assert capture.call_count == 1
        assert capture.call_args.args[0]["label"] == "flow-seat2"
        run = json.loads(run_path.read_text(encoding="utf-8"))
    assert run["resumedFrom"] == "earlier"
    assert [row["label"] for row in run["seats"]] == ["digen-01", "flow-seat2"]
    assert run["consumerProofs"][0]["host"] == "labs.google"


def test_video_capture_command_targets_exact_declared_seat() -> None:
    account = {"profile": "seat2", "port": 9224, "label": "flow-seat2", "provider": "flow",
               "host": "labs.google", "url": "https://labs.google/fx/tools/flow/project/project-id"}
    with patch.object(fleet, "run_bounded_child", side_effect=[0, 1]) as run:
        row = fleet.capture_and_graduate_video(account, 99.0, 77.0)
    sso_command, command = [call.args[0] for call in run.call_args_list]
    assert "--include-video" in sso_command
    assert sso_command[sso_command.index("--host-exact") + 1] == "labs.google"
    assert command[command.index("--port") + 1] == "9224"
    assert command[command.index("--match") + 1] == account["url"]
    assert command[command.index("--host") + 1] == "labs.google"
    assert command[command.index("--seat") + 1] == "flow-seat2"
    assert row["state"] == "NOT_ADMITTED"


def test_video_parent_timeout_persists_terminal_sso_failure_without_capture() -> None:
    account = {"profile": "niloy", "port": 9223, "label": "niloy-1", "provider": "flow",
               "host": "labs.google", "url": "https://labs.google/fx/tools/flow/project/project-id"}
    with patch.object(fleet, "run_bounded_child", return_value=None) as run:
        row = fleet.capture_and_graduate_video(account, 99.0, 77.0)
    assert run.call_count == 1
    assert row["ssoRc"] == "PARENT_TIMEOUT"
    assert row["state"] == "NOT_ADMITTED"
    assert "parent deadline" in row["detail"]


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} FLEET GRADUATION TESTS PASSED")


if __name__ == "__main__":
    main()
