"""Offline command-contract checks for the master graduation coordinator."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import json
import pathlib
import tempfile

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


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} FLEET GRADUATION TESTS PASSED")


if __name__ == "__main__":
    main()
