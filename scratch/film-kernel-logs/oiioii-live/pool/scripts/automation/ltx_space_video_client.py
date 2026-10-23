"""Stateless LTX Video client for the public Hugging Face Gradio Space.

The Space exposes a public Gradio queue contract, so this seat needs neither a
browser nor a fabricated API key.  A configured ``hf_`` token is accepted but
never required, printed, or forwarded to a cross-origin media URL.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional

from gradio_space_client import (
    GradioSpaceClient,
    GradioSpaceError,
    find_file_ref,
    is_mp4_bytes,
)
from veo_session_replay import SessionExpired
from veoaifree_chat_client import ChatError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = "https://lightricks-ltx-video-distilled.hf.space"
DEFAULT_API_NAME = "text_to_video"
DEFAULT_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted"
ARTIFACT_DIR = ROOT / "state" / "harvest" / "ltx_space"
_HF_SPACE_RE = re.compile(r"^https://[A-Za-z0-9.-]+\.hf\.space$")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _prompt(messages: List[Dict[str, Any]]) -> str:
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return " ".join(
                str(part.get("text") or "").strip()
                for part in content
                if isinstance(part, dict) and part.get("type") in (None, "text")
            ).strip()
    return ""


def _number(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fallback
    return min(maximum, max(minimum, float(value)))


def _dimension(value: Any, fallback: int) -> int:
    return int(round(_number(value, fallback, 256, 1280) / 32) * 32)


def _frames(value: Any) -> int:
    bounded = int(round(_number(value, 9, 9, 257)))
    return min(257, max(9, round((bounded - 1) / 8) * 8 + 1))


class LtxSpaceVideoClient:
    """One public, zero-dollar LTX Space seat in the SessionPool contract."""

    def __init__(
        self,
        secret: Path | str,
        timeout: int = 900,
        *,
        client_factory: Callable[..., GradioSpaceClient] = GradioSpaceClient,
        artifact_dir: Path = ARTIFACT_DIR,
    ) -> None:
        self.path = Path(secret)
        raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        api = raw.get("api") if isinstance(raw.get("api"), dict) else {}
        self.host = str(raw.get("host") or "lightricks-ltx-video-distilled.hf.space")
        self.base = str(api.get("base") or DEFAULT_BASE).strip().rstrip("/")
        if not _HF_SPACE_RE.fullmatch(self.base):
            raise ChatError("BAD_CONFIG", "LTX Space base must be https://*.hf.space")
        self.api_name = str(api.get("api_name") or DEFAULT_API_NAME).strip().lstrip("/")
        if self.api_name != DEFAULT_API_NAME:
            raise ChatError("BAD_CONFIG", "LTX Space seat must use text_to_video")
        self.timeout = int(_number(api.get("timeout"), timeout, 30, 900))
        token = str(api.get("token") or "").strip()
        if token and not token.startswith("hf_"):
            raise SessionExpired("BAD_TOKEN", "configured Hugging Face token is not an hf_ token")
        self._token = token or None
        self._defaults = api.get("defaults") if isinstance(api.get("defaults"), dict) else {}
        self._client_factory = client_factory
        self.artifact_dir = Path(artifact_dir)
        self.confirm_spend = _truthy(os.environ.get("OMNI_VIDEO_CONFIRM_SPEND"))

    def _data(self, prompt: str, duration_seconds: Optional[int] = None) -> list[Any]:
        defaults = self._defaults
        duration = _number(defaults.get("duration"), 2, 0.3, 8.5)
        frames = _frames(defaults.get("frames"))
        if duration_seconds is not None:
            if not 1 <= float(duration_seconds) <= 8.5:
                raise ChatError("DURATION_UNSUPPORTED", "LTX shot duration must be within 1 to 8.5 seconds")
            duration = float(duration_seconds)
            frames = _frames(round(duration * 24) + 1)
        return [
            prompt,
            str(defaults.get("negative_prompt") or DEFAULT_NEGATIVE),
            None,
            None,
            _dimension(defaults.get("height"), 512),
            _dimension(defaults.get("width"), 704),
            "text-to-video",
            duration,
            frames,
            int(round(_number(defaults.get("seed"), 42, 0, 4_294_967_295))),
            defaults.get("randomize_seed") is not False,
            _number(defaults.get("guidance_scale"), 3, 1, 10),
            defaults.get("improve_texture") is not False,
        ]

    def _archive(self, raw: bytes) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(raw).hexdigest()[:16]
        name = f"ltx_{time.strftime('%Y%m%dT%H%M%S')}_{digest}.mp4"
        target = self.artifact_dir / name
        temporary = target.with_suffix(".mp4.tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, target)
        return target

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        if not self.confirm_spend:
            raise ChatError(
                "SPEND_GATE_CLOSED",
                "LTX Space submit refused: set OMNI_VIDEO_CONFIRM_SPEND=1",
            )
        prompt = _prompt(messages)
        if not prompt:
            raise ChatError("EMPTY_PROMPT", "LTX Space video prompt is required")

        client = self._client_factory(self.base, timeout=self.timeout)
        try:
            terminal = client.submit_and_poll(
                self.api_name, self._data(prompt, duration_seconds=duration_seconds), token=self._token
            )
            ref = find_file_ref(terminal.data, self.base)
            if ref is None:
                raise ChatError("NO_VIDEO_URL", "LTX Space completed without a video file")
            media = client.download_file(ref, token=self._token)
        except GradioSpaceError as exc:
            if exc.status in (401, 403) and self._token:
                raise SessionExpired("AUTH", "Hugging Face rejected the configured token")
            code = "RATE" if exc.status == 429 else "SPACE_ERROR"
            raise ChatError(code, str(exc)[:300], status=exc.status)

        if not is_mp4_bytes(media):
            raise ChatError("INVALID_MP4", "LTX Space returned a non-MP4 artifact")
        artifact = self._archive(media)
        return {
            "text": ref.url,
            "video_url": ref.url,
            "model": model or "Lightricks/LTX-Video-0.9.8-distilled",
            "label": "huggingface/ltx-video-distilled",
            "status": 200,
            "credits_spent": 0.0,
            "raw_len": len(media),
            "artifact_path": str(artifact),
        }


__all__ = ["LtxSpaceVideoClient"]
