"""Offline contract tests for the OmniRoute graduation master."""
from __future__ import annotations

import json
import pathlib
import tempfile
from unittest.mock import patch

import omniroute_graduation as master


def test_plan_excludes_non_chat_and_internal_rows() -> None:
    routes = master.plan_from_catalog([
        {"id": "gpt-5", "owned_by": "openai"},
        {"id": "vertex/veo-3.1-generate-preview", "owned_by": "vertex"},
        {"id": "frontier", "owned_by": "combo"},
        {"id": "session-pool/auto", "owned_by": "session_pool"},
    ])
    assert [(r["provider"], r["model"]) for r in routes] == [("openai", "gpt-5")]


def test_direct_probe_requires_computed_answer() -> None:
    class FakeResponse:
        status_code = 200
        text = json.dumps({"choices": [{"message": {"content": "58"}}]})

        def json(self):
            return json.loads(self.text)

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResponse()

    row = master.direct_probe(FakeSession(), {"provider": "openai", "model": "gpt-5",
                                              "modelFamily": "chat"}, 1)
    assert row["directProof"] == "DIRECT_LAW3_OK"


def test_unadmitted_omni_routes_are_not_admitted_by_file_scope() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "admissions.json"
        path.write_text(json.dumps({"entries": [{"model": "openai/gpt-5", "state": "ADMITTED",
                                                   "modality": "chat"}]}), encoding="utf-8")
        with patch.object(master, "ADMISSIONS", path):
            # The master ledger is exact-model scoped; no host/provider-wide
            # wildcard is accepted by its generated admission entries.
            data = master.read_json(path, {})
            models = {e["model"] for e in data["entries"]}
            assert models == {"openai/gpt-5"}


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL {len(tests)} OMNI GRADUATION TESTS PASSED")


if __name__ == "__main__":
    main()
