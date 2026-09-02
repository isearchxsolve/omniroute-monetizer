from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from gradio_space_client import GradioEvent  # noqa: E402
from ltx_space_video_client import LtxSpaceVideoClient  # noqa: E402
from veoaifree_chat_client import ChatError  # noqa: E402


MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


class FakeSpaceClient:
    instances = []
    media = MP4

    def __init__(self, base_url: str, timeout: int) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.calls = []
        type(self).instances.append(self)

    def submit_and_poll(self, api_name, data, *, token=None):
        self.calls.append((api_name, data, token))
        return GradioEvent(
            name="complete",
            data=[{"url": "/gradio_api/file=result.mp4", "mime_type": "video/mp4"}],
        )

    def download_file(self, ref, *, token=None):
        self.calls.append(("download", ref.url, token))
        return type(self).media


def _seat(tmp_path: Path) -> Path:
    path = tmp_path / "session_ltx_space_public.json"
    path.write_text(
        json.dumps(
            {
                "host": "lightricks-ltx-video-distilled.hf.space",
                "modality": "video",
                "api": {
                    "kind": "hf_ltx_space",
                    "base": "https://lightricks-ltx-video-distilled.hf.space",
                    "api_name": "text_to_video",
                    "defaults": {"randomize_seed": False},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_submit_contract_download_gate_and_archive(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNI_VIDEO_CONFIRM_SPEND", "1")
    FakeSpaceClient.instances.clear()
    FakeSpaceClient.media = MP4
    client = LtxSpaceVideoClient(
        _seat(tmp_path), client_factory=FakeSpaceClient, artifact_dir=tmp_path / "media"
    )

    result = client.chat([{"role": "user", "content": "ocean lighthouse"}])

    fake = FakeSpaceClient.instances[-1]
    api_name, data, token = fake.calls[0]
    assert api_name == "text_to_video"
    assert len(data) == 13
    assert data == [
        "ocean lighthouse",
        "worst quality, inconsistent motion, blurry, jittery, distorted",
        None,
        None,
        512,
        704,
        "text-to-video",
        2,
        9,
        42,
        False,
        3,
        True,
    ]
    assert token is None
    assert result["video_url"].endswith("result.mp4")
    assert result["credits_spent"] == 0.0
    artifacts = list((tmp_path / "media").glob("*.mp4"))
    assert len(artifacts) == 1
    assert artifacts[0].read_bytes() == MP4


def test_spend_gate_is_closed_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMNI_VIDEO_CONFIRM_SPEND", raising=False)
    client = LtxSpaceVideoClient(_seat(tmp_path), client_factory=FakeSpaceClient)
    with pytest.raises(ChatError, match="SPEND_GATE_CLOSED|submit refused"):
        client.chat([{"role": "user", "content": "ocean"}])


def test_non_mp4_result_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNI_VIDEO_CONFIRM_SPEND", "1")
    FakeSpaceClient.media = b"not video"
    client = LtxSpaceVideoClient(
        _seat(tmp_path), client_factory=FakeSpaceClient, artifact_dir=tmp_path / "media"
    )
    with pytest.raises(ChatError, match="INVALID_MP4|non-MP4"):
        client.chat([{"role": "user", "content": "ocean"}])
    assert not list((tmp_path / "media").glob("*.mp4"))
