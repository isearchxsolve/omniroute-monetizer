from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "automation" / "omni_video_runtime_patch.py"
SPEC = importlib.util.spec_from_file_location("omni_video_runtime_patch", MODULE_PATH)
assert SPEC and SPEC.loader
PATCH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PATCH
SPEC.loader.exec_module(PATCH)


class OmniVideoRuntimePatchTests(unittest.TestCase):
    def test_route_chunk_resolution_uses_next_server_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            route = root / "dist" / ".build" / "next" / "server" / "app" / "api" / "v1" / "videos" / "generations" / "route.js"
            chunk = root / "dist" / ".build" / "next" / "server" / "chunks" / "video.js"
            route.parent.mkdir(parents=True)
            chunk.parent.mkdir(parents=True)
            route.write_text('R.c("server/chunks/video.js")', encoding="utf-8")
            chunk.write_text("video-handler", encoding="utf-8")

            self.assertEqual(PATCH.video_route_chunks(root), [chunk])

    def test_model_specific_kie_fields_are_in_source_patch(self) -> None:
        self.assertIn('input.mode = typeof body.mode === "string" ? body.mode : "std";', PATCH.KIE_SOURCE_NEW)
        self.assertIn('input.multi_shots = typeof body.multi_shots === "boolean" ? body.multi_shots : false;', PATCH.KIE_SOURCE_NEW)
        self.assertIn('input.resolution = typeof body.resolution === "string" ? body.resolution : "480p";', PATCH.KIE_SOURCE_NEW)
        self.assertIn("mode?: unknown;", PATCH.KIE_SOURCE_TYPE_NEW)
        self.assertIn("multi_shots?: unknown;", PATCH.KIE_SOURCE_TYPE_NEW)
        self.assertIn("resolution?: unknown;", PATCH.KIE_SOURCE_TYPE_NEW)

    def test_each_replacement_is_exactly_reversible(self) -> None:
        replacements = [
            PATCH.Replacement("vertex", "vertex.txt", PATCH.VERTEX_SOURCE_OLD, PATCH.VERTEX_SOURCE_NEW),
            PATCH.Replacement("kie-type", "kie-type.txt", PATCH.KIE_SOURCE_TYPE_OLD, PATCH.KIE_SOURCE_TYPE_NEW),
            PATCH.Replacement("kie-source", "kie-source.txt", PATCH.KIE_SOURCE_OLD, PATCH.KIE_SOURCE_NEW),
            PATCH.Replacement("vertex-runtime", "vertex-runtime.txt", PATCH.VERTEX_RUNTIME_OLD, PATCH.VERTEX_RUNTIME_NEW),
            PATCH.Replacement("kie-runtime", "kie-runtime.txt", PATCH.KIE_RUNTIME_OLD, PATCH.KIE_RUNTIME_NEW),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for replacement in replacements:
                path = root / replacement.relative_path
                path.write_text(replacement.old, encoding="utf-8")
                checked = PATCH.check_replacement(replacement, root)
                self.assertEqual(checked[1], 1)
                self.assertEqual(checked[3], "pending")
                path.write_text(replacement.old.replace(replacement.old, replacement.new, 1), encoding="utf-8")
                checked = PATCH.check_replacement(replacement, root)
                self.assertEqual(checked[3], "applied")


if __name__ == "__main__":
    unittest.main()
