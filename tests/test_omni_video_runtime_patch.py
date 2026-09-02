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

    def test_runtime_chunk_locator_accepts_final_preview_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            route = root / "dist" / ".build" / "next" / "server" / "app" / "api" / "v1" / "videos" / "generations" / "route.js"
            chunk = root / "dist" / ".build" / "next" / "server" / "chunks" / "video.js"
            route.parent.mkdir(parents=True)
            chunk.parent.mkdir(parents=True)
            route.write_text('R.c("server/chunks/video.js")', encoding="utf-8")
            chunk.write_text(PATCH.VERTEX_RUNTIME_PREVIEW_NEW, encoding="utf-8")

            self.assertEqual(
                PATCH.find_runtime_chunk(
                    root,
                    PATCH.VERTEX_RUNTIME_OLD,
                    PATCH.VERTEX_RUNTIME_NEW,
                    "Vertex registry",
                    alternatives=(PATCH.VERTEX_RUNTIME_PREVIEW_NEW,),
                ),
                chunk,
            )

    def test_model_specific_kie_fields_are_in_source_patch(self) -> None:
        self.assertIn('input.mode = typeof body.mode === "string" ? body.mode : "std";', PATCH.KIE_SOURCE_NEW)
        self.assertIn('input.multi_shots = typeof body.multi_shots === "boolean" ? body.multi_shots : false;', PATCH.KIE_SOURCE_NEW)
        self.assertIn('input.resolution = typeof body.resolution === "string" ? body.resolution : "480p";', PATCH.KIE_SOURCE_NEW)
        self.assertIn("mode?: unknown;", PATCH.KIE_SOURCE_TYPE_NEW)
        self.assertIn("multi_shots?: unknown;", PATCH.KIE_SOURCE_TYPE_NEW)
        self.assertIn("resolution?: unknown;", PATCH.KIE_SOURCE_TYPE_NEW)

    def test_vertex_preview_registry_contains_connection_advertised_ids(self) -> None:
        self.assertIn('veo-3.1-generate-preview', PATCH.VERTEX_SOURCE_PREVIEW_NEW)
        self.assertIn('veo-3.1-fast-generate-preview', PATCH.VERTEX_SOURCE_PREVIEW_NEW)
        self.assertIn('veo-3.1-lite-generate-preview', PATCH.VERTEX_SOURCE_PREVIEW_NEW)
        self.assertIn('veo-3.1-generate-preview', PATCH.VERTEX_RUNTIME_PREVIEW_NEW)
        self.assertIn('veo-3.1-fast-generate-preview', PATCH.VERTEX_RUNTIME_PREVIEW_NEW)

    def test_huggingface_video_contract_is_explicit_and_mp4_gated(self) -> None:
        self.assertIn('format: "huggingface-video"', PATCH.HUGGINGFACE_SOURCE_REGISTRY_NEW)
        self.assertIn('tencent/HunyuanVideo', PATCH.HUGGINGFACE_SOURCE_REGISTRY_NEW)
        self.assertIn('Wan-AI/Wan2.2-TI2V-5B', PATCH.HUGGINGFACE_SOURCE_REGISTRY_NEW)
        self.assertIn('meituan-longcat/LongCat-Video', PATCH.HUGGINGFACE_SOURCE_REGISTRY_NEW)
        self.assertIn('/fal-ai/${route}?_subdomain=queue', PATCH.HUGGINGFACE_SOURCE_FUNCTION)
        self.assertIn('response_url', PATCH.HUGGINGFACE_SOURCE_FUNCTION)
        self.assertIn('VIDEO_ARTIFACT_UNAVAILABLE', PATCH.HUGGINGFACE_SOURCE_FUNCTION)
        self.assertIn('token.startsWith("hf_")', PATCH.HUGGINGFACE_SOURCE_FUNCTION)
        self.assertIn('__omniHuggingFaceVideo', PATCH.HUGGINGFACE_RUNTIME_BRANCH_NEW)

    def test_ltx_zerogpu_contract_is_explicit_and_not_admitted_by_default(self) -> None:
        self.assertEqual(PATCH.HUGGINGFACE_SPACE_MODEL, "Lightricks/LTX-Video-0.9.8-distilled")
        self.assertIn(PATCH.HUGGINGFACE_SPACE_MODEL, PATCH.HUGGINGFACE_SPACE_SOURCE_REGISTRY_NEW)
        self.assertIn(PATCH.HUGGINGFACE_SPACE_MODEL, PATCH.HUGGINGFACE_SPACE_RUNTIME_REGISTRY_NEW)
        self.assertIn('https://lightricks-ltx-video-distilled.hf.space', PATCH.GRADIO_SPACE_SOURCE_FUNCTION)
        self.assertIn('/gradio_api/call/${HUGGINGFACE_SPACE_LTX_API_NAME}', PATCH.GRADIO_SPACE_SOURCE_FUNCTION)
        self.assertIn('text-to-video', PATCH.GRADIO_SPACE_SOURCE_FUNCTION)
        self.assertIn('VIDEO_ARTIFACT_UNAVAILABLE', PATCH.GRADIO_SPACE_SOURCE_FUNCTION)
        self.assertIn('LTX ZeroGPU Space poll closed without a terminal event', PATCH.GRADIO_SPACE_SOURCE_FUNCTION)
        self.assertIn('__omniHuggingFaceLtxSpaceVideo', PATCH.GRADIO_SPACE_RUNTIME_FUNCTION)
        self.assertIn('huggingface-zerogpu', PATCH.GRADIO_SPACE_RUNTIME_FUNCTION)

    def test_ltx_follow_up_replacements_are_exactly_reversible(self) -> None:
        replacements = [
            PATCH.Replacement("ltx-source-registry", "registry.ts", PATCH.HUGGINGFACE_SPACE_SOURCE_REGISTRY_OLD, PATCH.HUGGINGFACE_SPACE_SOURCE_REGISTRY_NEW),
            PATCH.Replacement("ltx-runtime-registry", "registry.js", PATCH.HUGGINGFACE_SPACE_RUNTIME_REGISTRY_OLD, PATCH.HUGGINGFACE_SPACE_RUNTIME_REGISTRY_NEW),
            PATCH.Replacement("ltx-source-dispatch", "handler.ts", PATCH.HUGGINGFACE_SPACE_SOURCE_DISPATCH_OLD, PATCH.HUGGINGFACE_SPACE_SOURCE_DISPATCH_NEW),
            PATCH.Replacement("ltx-runtime-dispatch", "handler.js", PATCH.HUGGINGFACE_SPACE_RUNTIME_DISPATCH_OLD, PATCH.HUGGINGFACE_SPACE_RUNTIME_DISPATCH_NEW),
            PATCH.Replacement("ltx-source-handler", "handler.ts", PATCH.GRADIO_SPACE_SOURCE_FUNCTION_MARKER, PATCH.GRADIO_SPACE_SOURCE_FUNCTION_NEW),
            PATCH.Replacement("ltx-runtime-handler", "handler.js", PATCH.GRADIO_SPACE_RUNTIME_FUNCTION_MARKER, PATCH.GRADIO_SPACE_RUNTIME_FUNCTION_NEW),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for replacement in replacements:
                path = root / replacement.relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(replacement.old, encoding="utf-8")
                self.assertEqual(PATCH.check_replacement(replacement, root)[3], "pending")
                path.write_text(replacement.new, encoding="utf-8")
                self.assertEqual(PATCH.check_replacement(replacement, root)[3], "applied")

    def test_huggingface_replacements_are_exactly_reversible(self) -> None:
        replacements = [
            PATCH.Replacement("hf-source-registry", "registry.ts", PATCH.HUGGINGFACE_SOURCE_REGISTRY_OLD, PATCH.HUGGINGFACE_SOURCE_REGISTRY_NEW),
            PATCH.Replacement("hf-runtime-registry", "registry.js", PATCH.HUGGINGFACE_RUNTIME_REGISTRY_OLD, PATCH.HUGGINGFACE_RUNTIME_REGISTRY_NEW),
            PATCH.Replacement("hf-source-branch", "handler.ts", PATCH.HUGGINGFACE_SOURCE_BRANCH_OLD, PATCH.HUGGINGFACE_SOURCE_BRANCH_NEW),
            PATCH.Replacement("hf-source-handler", "handler.ts", PATCH.HUGGINGFACE_SOURCE_FUNCTION_MARKER, PATCH.HUGGINGFACE_SOURCE_FUNCTION_NEW),
            PATCH.Replacement("hf-runtime-branch", "handler.js", PATCH.HUGGINGFACE_RUNTIME_BRANCH_OLD, PATCH.HUGGINGFACE_RUNTIME_BRANCH_NEW),
            PATCH.Replacement("hf-runtime-handler", "handler.js", PATCH.HUGGINGFACE_RUNTIME_FUNCTION_MARKER, PATCH.HUGGINGFACE_RUNTIME_FUNCTION_NEW),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for replacement in replacements:
                path = root / replacement.relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(replacement.old, encoding="utf-8")
                self.assertEqual(PATCH.check_replacement(replacement, root)[3], "pending")
                path.write_text(replacement.new, encoding="utf-8")
                self.assertEqual(PATCH.check_replacement(replacement, root)[3], "applied")

    def test_kie_veo_uses_dedicated_generate_and_status_endpoints(self) -> None:
        self.assertIn('/api/v1/veo/generate', PATCH.KIE_SOURCE_VEO_BRANCH)
        self.assertIn('/api/v1/veo/record-info', PATCH.KIE_SOURCE_VEO_BRANCH)
        self.assertIn('model: kieModel', PATCH.KIE_SOURCE_VEO_BRANCH)
        self.assertIn('generationType: "TEXT_2_VIDEO"', PATCH.KIE_SOURCE_VEO_BRANCH)
        self.assertIn('/api/v1/veo/generate', PATCH.KIE_RUNTIME_VEO_BRANCH)
        self.assertIn('/api/v1/veo/record-info', PATCH.KIE_RUNTIME_VEO_BRANCH)
        self.assertIn('model:`${t}/${e}`', PATCH.KIE_RUNTIME_VEO_BRANCH)
        self.assertIn('KIE Veo create response missing taskId', PATCH.KIE_SOURCE_VEO_DIAGNOSTIC_NEW)
        self.assertIn('createRec.data', PATCH.KIE_RUNTIME_VEO_DIAGNOSTIC_NEW)

    def test_each_replacement_is_exactly_reversible(self) -> None:
        replacements = [
            PATCH.Replacement("vertex", "vertex.txt", PATCH.VERTEX_SOURCE_OLD, PATCH.VERTEX_SOURCE_NEW),
            PATCH.Replacement("vertex-preview", "vertex-preview.txt", PATCH.VERTEX_SOURCE_PREVIEW_OLD, PATCH.VERTEX_SOURCE_PREVIEW_NEW),
            PATCH.Replacement("kie-type", "kie-type.txt", PATCH.KIE_SOURCE_TYPE_OLD, PATCH.KIE_SOURCE_TYPE_NEW),
            PATCH.Replacement("kie-source", "kie-source.txt", PATCH.KIE_SOURCE_OLD, PATCH.KIE_SOURCE_NEW),
            PATCH.Replacement("kie-veo-source", "kie-veo-source.txt", PATCH.KIE_SOURCE_VEO_MARKER, PATCH.KIE_SOURCE_VEO_BRANCH + PATCH.KIE_SOURCE_VEO_MARKER),
            PATCH.Replacement("kie-veo-source-diagnostic", "kie-veo-source-diagnostic.txt", PATCH.KIE_SOURCE_VEO_DIAGNOSTIC_OLD, PATCH.KIE_SOURCE_VEO_DIAGNOSTIC_NEW),
            PATCH.Replacement("vertex-runtime", "vertex-runtime.txt", PATCH.VERTEX_RUNTIME_OLD, PATCH.VERTEX_RUNTIME_NEW),
            PATCH.Replacement("vertex-runtime-preview", "vertex-runtime-preview.txt", PATCH.VERTEX_RUNTIME_PREVIEW_OLD, PATCH.VERTEX_RUNTIME_PREVIEW_NEW),
            PATCH.Replacement("kie-runtime", "kie-runtime.txt", PATCH.KIE_RUNTIME_OLD, PATCH.KIE_RUNTIME_NEW),
            PATCH.Replacement("kie-veo-runtime", "kie-veo-runtime.txt", PATCH.KIE_RUNTIME_VEO_MARKER, PATCH.KIE_RUNTIME_VEO_BRANCH + PATCH.KIE_RUNTIME_VEO_MARKER),
            PATCH.Replacement("kie-veo-runtime-diagnostic", "kie-veo-runtime-diagnostic.txt", PATCH.KIE_RUNTIME_VEO_DIAGNOSTIC_OLD, PATCH.KIE_RUNTIME_VEO_DIAGNOSTIC_NEW),
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

    def test_kie_branch_remains_applied_after_diagnostic_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.ts"
            source.write_text(
                PATCH.KIE_SOURCE_VEO_BRANCH.replace(
                    PATCH.KIE_SOURCE_VEO_DIAGNOSTIC_OLD,
                    PATCH.KIE_SOURCE_VEO_DIAGNOSTIC_NEW,
                )
                + PATCH.KIE_SOURCE_VEO_MARKER,
                encoding="utf-8",
            )
            replacement = PATCH.Replacement(
                "KIE source Veo API branch",
                "source.ts",
                PATCH.KIE_SOURCE_VEO_MARKER,
                PATCH.KIE_SOURCE_VEO_BRANCH + PATCH.KIE_SOURCE_VEO_MARKER,
            )
            self.assertEqual(PATCH.check_replacement(replacement, root)[3], "applied")

            runtime = root / "runtime.js"
            runtime.write_text(
                PATCH.KIE_RUNTIME_VEO_BRANCH.replace(
                    PATCH.KIE_RUNTIME_VEO_DIAGNOSTIC_OLD,
                    PATCH.KIE_RUNTIME_VEO_DIAGNOSTIC_NEW,
                )
                + PATCH.KIE_RUNTIME_VEO_MARKER,
                encoding="utf-8",
            )
            replacement = PATCH.Replacement(
                "KIE compiled Veo API branch",
                "runtime.js",
                PATCH.KIE_RUNTIME_VEO_MARKER,
                PATCH.KIE_RUNTIME_VEO_BRANCH + PATCH.KIE_RUNTIME_VEO_MARKER,
            )
            self.assertEqual(PATCH.check_replacement(replacement, root)[3], "applied")

    def test_original_registry_remains_applied_after_preview_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.ts"
            source.write_text(PATCH.VERTEX_SOURCE_PREVIEW_NEW, encoding="utf-8")
            replacement = PATCH.Replacement(
                "Vertex source registry",
                "source.ts",
                PATCH.VERTEX_SOURCE_OLD,
                PATCH.VERTEX_SOURCE_NEW,
            )
            self.assertEqual(PATCH.check_replacement(replacement, root)[3], "applied")

            runtime = root / "runtime.js"
            runtime.write_text(PATCH.VERTEX_RUNTIME_PREVIEW_NEW, encoding="utf-8")
            replacement = PATCH.Replacement(
                "Vertex compiled registry",
                "runtime.js",
                PATCH.VERTEX_RUNTIME_OLD,
                PATCH.VERTEX_RUNTIME_NEW,
            )
            self.assertEqual(PATCH.check_replacement(replacement, root)[3], "applied")


if __name__ == "__main__":
    unittest.main()
