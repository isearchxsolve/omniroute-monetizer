from __future__ import annotations

import json
import sys
from pathlib import Path


AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from gradio_space_client import (  # noqa: E402
    GradioSpaceClient,
    GradioSpaceError,
    find_file_ref,
    is_mp4_bytes,
)


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def read(self, _limit: int | None = None) -> bytes:
        return self.body


class FakeOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, request, timeout: float):
        self.requests.append((request, timeout))
        return next(self.responses)


def test_discovery_submit_and_poll_use_gradio_queue_contract() -> None:
    opener = FakeOpener(
        [
            FakeResponse(b'{"paths":{"/run/generate_video":{}}}'),
            FakeResponse(b'{"event_id":"event-123"}', status=202),
            FakeResponse(
                b'event: generating\n'
                b'data: {"msg":"progress"}\n\n'
                b'event: complete\n'
                b'data: [{"path":"/tmp/result.mp4","mime_type":"video/mp4"},7]\n\n'
                b'data: [DONE]\n\n'
            ),
        ]
    )
    client = GradioSpaceClient("https://space.example", opener=opener)

    assert "/run/generate_video" in client.openapi()["paths"]
    event_id = client.submit("generate_video", [None, "a moving ocean", 4])
    result = client.poll("generate_video", event_id)

    assert event_id == "event-123"
    assert result.name == "complete"
    assert result.data[0]["path"] == "/tmp/result.mp4"
    assert opener.requests[1][0].full_url == "https://space.example/gradio_api/call/generate_video"
    assert json.loads(opener.requests[1][0].data.decode("utf-8")) == {"data": [None, "a moving ocean", 4]}


def test_token_is_sent_only_as_auth_header_and_not_in_payload() -> None:
    opener = FakeOpener([FakeResponse(b'{"event_id":"e"}', status=202)])
    client = GradioSpaceClient("https://space.example", opener=opener)

    client.submit("generate_video", ["prompt"], token="hf_test_redacted")

    request = opener.requests[0][0]
    assert request.get_header("Authorization") == "Bearer hf_test_redacted"
    assert b"hf_test_redacted" not in request.data


def test_file_reference_and_mp4_gate_are_separate() -> None:
    ref = find_file_ref(
        [{"path": "/tmp/result.mp4", "mime_type": "video/mp4"}, 123],
        "https://space.example",
    )

    assert ref is not None
    assert ref.url == "https://space.example/gradio_api/file=/tmp/result.mp4"
    assert ref.mime_type == "video/mp4"
    assert is_mp4_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16)
    assert not is_mp4_bytes(b"not an mp4")


def test_file_download_is_bounded_and_auth_stays_same_origin() -> None:
    mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
    opener = FakeOpener([FakeResponse(mp4), FakeResponse(mp4)])
    client = GradioSpaceClient("https://space.example", opener=opener)

    same_origin = find_file_ref("/result.mp4", client.base_url)
    assert same_origin is not None
    assert client.download_file(same_origin, token="hf_test_redacted") == mp4
    assert opener.requests[0][0].get_header("Authorization") == "Bearer hf_test_redacted"

    external = find_file_ref("https://cdn.example/result.mp4", client.base_url)
    assert external is not None
    assert client.download_file(external, token="hf_test_redacted") == mp4
    assert opener.requests[1][0].get_header("Authorization") is None


def test_file_download_rejects_oversize_body() -> None:
    opener = FakeOpener([FakeResponse(b"x" * 9)])
    client = GradioSpaceClient("https://space.example", opener=opener)
    ref = find_file_ref("/result.mp4", client.base_url)
    assert ref is not None

    try:
        client.download_file(ref, max_bytes=8)
    except GradioSpaceError as exc:
        assert "safety limit" in str(exc)
    else:
        raise AssertionError("oversize download must fail closed")


def test_poll_without_terminal_event_is_not_admitted() -> None:
    opener = FakeOpener([FakeResponse(b'event: generating\ndata: {"msg":"progress"}\n\n')])
    client = GradioSpaceClient("https://space.example", opener=opener)

    try:
        client.poll("generate_video", "event-123")
    except GradioSpaceError as exc:
        assert "without a terminal event" in str(exc)
    else:
        raise AssertionError("poll must reject a stream without a terminal event")
