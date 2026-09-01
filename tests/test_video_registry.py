from __future__ import annotations

import sys
from pathlib import Path


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
sys.path.insert(0, str(AUTOMATION))

import video_registry as vr  # noqa: E402


def _build_route_fixture(tmp_path: Path, chunk_source: str) -> Path:
    dist = tmp_path / "dist"
    chunks = dist / ".build" / "next" / "server" / "chunks"
    route_dir = (
        dist
        / ".build"
        / "next"
        / "server"
        / "app"
        / "api"
        / "v1"
        / "videos"
        / "generations"
    )
    chunks.mkdir(parents=True)
    route_dir.mkdir(parents=True)
    (chunks / "video-config.js").write_text(chunk_source, encoding="utf-8")
    (route_dir / "route.js").write_text(
        'R.c("server/chunks/video-config.js")\n', encoding="utf-8"
    )
    return dist


def test_loads_accessor_exported_3850_video_registry(tmp_path: Path) -> None:
    dist = _build_route_fixture(
        tmp_path,
        'let t={alpha:{id:"alpha",format:"openai-video",authType:"apikey",'
        'models:[{id:"t2v",name:"T2V"}]},adobe:{id:"adobe",'
        'format:"adobe-firefly-video",models:(0,r.toRegistryVideoModels)()}};'
        'e.s(["getVideoProvider",0,function(e){return t[e]||null},'
        '"getAllVideoModels",0,function(){return[]}]);',
    )

    registry = vr.load_registry("VIDEO_PROVIDERS", dist)

    assert registry["alpha"]["models"][0]["id"] == "t2v"
    assert registry["adobe"]["models"] == []
    assert registry["adobe"]["modelsUnresolved"] is True


def test_supported_formats_searches_only_video_route_dependencies(tmp_path: Path) -> None:
    dist = _build_route_fixture(
        tmp_path,
        'function x(y){return "openai-video"===y.format?1:'
        '"fal-ai-video"===y.format?2:'
        '{error:`Unsupported video format: ${y.format}`}}',
    )
    unrelated = dist / ".build" / "next" / "server" / "chunks" / "unrelated.js"
    unrelated.write_text(
        '"should-not-appear"===y.format; Unsupported video format', encoding="utf-8"
    )

    assert vr.supported_video_formats(dist) == ["fal-ai-video", "openai-video"]
