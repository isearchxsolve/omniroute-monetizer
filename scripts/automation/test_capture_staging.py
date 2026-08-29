"""Regression tests for staged, atomic CDP-capture output."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture_sessions_cdp import atomic_json_write  # noqa: E402


class CaptureStagingTests(unittest.TestCase):
    def test_atomic_write_replaces_complete_candidate_and_leaves_no_temp(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "candidate" / "session_example.json"
            atomic_json_write(target, {"host": "example.test", "status": {"alive": True}})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["host"], "example.test")
            self.assertFalse(target.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
