"""Regression tests for staged, atomic CDP-capture output."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture_sessions_cdp import atomic_json_write, validated_session_filename  # noqa: E402


class CaptureStagingTests(unittest.TestCase):
    def test_atomic_write_replaces_complete_candidate_and_leaves_no_temp(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "candidate" / "session_example.json"
            atomic_json_write(target, {"host": "example.test", "status": {"alive": True}})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["host"], "example.test")
            self.assertFalse(target.with_suffix(".json.tmp").exists())

    def test_per_tab_filename_must_stay_inside_the_capture_directory(self) -> None:
        self.assertEqual(
            validated_session_filename("session_9222_example_ABC123.json", "ignored"),
            "session_9222_example_ABC123.json",
        )
        with self.assertRaises(ValueError):
            validated_session_filename("..\\session_escape.json", "ignored")
        with self.assertRaises(ValueError):
            validated_session_filename("candidate.json", "ignored")


if __name__ == "__main__":
    unittest.main()
