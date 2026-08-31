"""Offline command-contract checks for the master graduation coordinator."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

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


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} FLEET GRADUATION TESTS PASSED")


if __name__ == "__main__":
    main()
