"""Regression tests for the non-echoable numeric graduation probe.

Run directly with:
    python scripts/automation/test_replay_check_law3.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_check import classify, keyword_in_body  # noqa: E402


class NumericLawThreeTests(unittest.TestCase):
    def test_raw_numeric_fallback_never_accepts_metadata(self) -> None:
        self.assertFalse(keyword_in_body('{"request_id":"abc58def"}', "58"))
        self.assertFalse(keyword_in_body('{"message":"unparsed response 58"}', "58"))

    def test_structurally_extracted_numeric_answer_passes(self) -> None:
        verdict, _ = classify("58", 200, None, "58")
        self.assertEqual(verdict, "REPLAY_OK")

    def test_numeric_answer_embedded_in_prose_does_not_graduate(self) -> None:
        verdict, _ = classify("The answer is 58", 200, None, "58")
        self.assertEqual(verdict, "NO_ANSWER")

    def test_alphabetic_phrase_diagnostic_fallback_still_has_meaningful_input(self) -> None:
        self.assertTrue(keyword_in_body('data: {"content":"the holy cow jumps"}', "holy cow"))


if __name__ == "__main__":
    unittest.main()
