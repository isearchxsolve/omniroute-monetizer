"""Regression tests for the non-echoable numeric graduation probe.

Run directly with:
    python scripts/automation/test_replay_check_law3.py
"""

from __future__ import annotations

import sys
import unittest
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_check import classify, keyword_in_body, replay  # noqa: E402


class NumericLawThreeTests(unittest.TestCase):
    def test_raw_phrase_in_metadata_cannot_override_failed_answer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session_test.json"
            path.write_text(json.dumps({"host": "example.test"}), encoding="utf-8")
            client = SimpleNamespace(chat=lambda messages: {
                "text": "", "status": 200,
                "raw": '{"title":"holy cow","answer":null}',
            })
            with patch("universal_replay.make_session_client", return_value=client):
                row = replay(path, "Say holy cow", "holy cow")
            self.assertNotEqual(row["verdict"], "REPLAY_OK")

    def test_exception_equal_to_answer_never_graduates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session_test.json"
            path.write_text(json.dumps({"host": "example.test"}), encoding="utf-8")
            with patch("universal_replay.make_session_client", side_effect=RuntimeError("58")):
                row = replay(path, "Compute 41 + 17", "58")
            self.assertNotEqual(row["verdict"], "REPLAY_OK")

    def test_raw_numeric_fallback_never_accepts_metadata(self) -> None:
        self.assertFalse(keyword_in_body('{"request_id":"abc58def"}', "58"))
        self.assertFalse(keyword_in_body('{"message":"unparsed response 58"}', "58"))

    def test_structurally_extracted_numeric_answer_passes(self) -> None:
        verdict, _ = classify("58", 200, None, "58")
        self.assertEqual(verdict, "REPLAY_OK")

    def test_numeric_answer_embedded_in_prose_does_not_graduate(self) -> None:
        verdict, _ = classify("The answer is 58", 200, None, "58")
        self.assertEqual(verdict, "NO_ANSWER")

    def test_upgrade_text_outweighs_ambiguous_http_403(self) -> None:
        verdict, _ = classify("You've used your access. Upgrade your plan.", 403, None, "58")
        self.assertEqual(verdict, "WALL")

    def test_bare_http_403_remains_an_authentication_failure(self) -> None:
        verdict, _ = classify("forbidden by upstream", 403, None, "58")
        self.assertEqual(verdict, "AUTH")

    def test_alphabetic_phrase_diagnostic_fallback_still_has_meaningful_input(self) -> None:
        self.assertTrue(keyword_in_body('data: {"content":"the holy cow jumps"}', "holy cow"))


if __name__ == "__main__":
    unittest.main()
