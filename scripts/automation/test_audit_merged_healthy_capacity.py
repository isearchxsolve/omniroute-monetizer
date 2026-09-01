#!/usr/bin/env python3
"""Offline contract tests for the merged-capacity evidence model."""
from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_merged_healthy_capacity import (
    model_capacity_rows,
    seat_capacity_rows,
    verified_omni_entries,
    verified_seat_entries,
)


class MergedCapacityEvidenceTests(unittest.TestCase):
    def test_omni_requires_both_direct_and_consumer_proof(self) -> None:
        rows = verified_omni_entries({"entries": [
            {"provider": "alpha", "model": "alpha/m1", "modality": "chat", "state": "ADMITTED",
             "directProof": "DIRECT_LAW3_OK", "consumerProof": "CONSUMER_LAW3_OK"},
            {"provider": "alpha", "model": "alpha/m2", "modality": "chat", "state": "ADMITTED",
             "directProof": "DIRECT_LAW3_OK", "consumerProof": "TRANSPORT"},
            {"provider": "beta", "model": "beta/m1", "modality": "chat", "state": "WALL",
             "directProof": "DIRECT_LAW3_OK", "consumerProof": "CONSUMER_LAW3_OK"},
        ]})
        self.assertEqual(rows, [{"provider": "alpha", "model": "alpha/m1", "modality": "chat"}])

    def test_omni_capacity_is_provider_by_distinct_concrete_model(self) -> None:
        rows = model_capacity_rows([
            {"provider": "alpha", "model": "alpha/m2", "modality": "chat"},
            {"provider": "alpha", "model": "alpha/m1", "modality": "chat"},
            {"provider": "alpha", "model": "alpha/m1", "modality": "chat"},
        ])
        self.assertEqual(rows[0]["verifiedModelCount"], 2)
        self.assertEqual(rows[0]["models"], ["alpha/m1", "alpha/m2"])

    def test_seat_capacity_is_session_count_not_fabricated_model_count(self) -> None:
        entries = verified_seat_entries({"entries": [
            {"state": "ADMITTED", "host": "chat.example", "sessionFile": "session_a.json", "modality": "chat"},
            {"state": "ADMITTED", "host": "chat.example", "sessionFile": "session_b.json", "modality": "chat"},
        ]})
        row = seat_capacity_rows(entries)[0]
        self.assertEqual(row["verifiedSessionCount"], 2)
        self.assertEqual(row["models"], [])
        self.assertEqual(row["modelIdentity"], "UNENUMERATED_BY_SESSION_ARTIFACT_NOT_COUNTED_AS_ONE_MODEL")


if __name__ == "__main__":
    unittest.main()
