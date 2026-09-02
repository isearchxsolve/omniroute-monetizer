"""Small, dependency-free client for a Gradio Space queue API.

This module deliberately stops at the transport boundary.  It can discover a
Space's public API, submit a named endpoint, consume its server-sent-event
queue stream, and normalize a returned file reference.  It does not submit a
generation request by itself, does not register a provider, and does not
declare a route healthy.  Callers must perform the project's existing MP4
artifact check before admission.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


JsonValue = Any
Opener = Callable[..., Any]


class GradioSpaceError(RuntimeError):
    """A bounded, non-secret-bearing Space transport error."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class GradioEvent:
    """One terminal or intermediate event from a Gradio queue stream."""

    name: str
    data: JsonValue


@dataclass(frozen=True)
class GradioFileRef:
    """A remote or Space-relative file reference returned by Gradio."""

    url: str
    name: str | None = None
    mime_type: str | None = None


TERMINAL_EVENTS = frozenset({"complete", "error", "cancelled"})


def _json_bytes(value: JsonValue) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_json(raw: bytes, *, context: str) -> JsonValue:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GradioSpaceError(f"Gradio {context} returned invalid JSON") from exc


def _read_response(response: Any) -> tuple[int, bytes]:
    status = int(getattr(response, "status", getattr(response, "code", 200)))
    raw = response.read()
    return status, raw


def _parse_sse(raw: bytes) -> list[GradioEvent]:
    """Parse the small SSE dialect emitted by Gradio's queue endpoint."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GradioSpaceError("Gradio queue returned non-UTF-8 events") from exc

    events: list[GradioEvent] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return
        data_text = "\n".join(data_lines)
        if data_text != "[DONE]":
            try:
                data: JsonValue = json.loads(data_text)
            except json.JSONDecodeError:
                data = data_text
            events.append(GradioEvent(name=event_name, data=data))
        event_name = "message"
        data_lines = []

    for line in text.splitlines():
        if not line:
            flush()
        elif line.startswith("event:"):
            event_name = line[6:].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        # SSE comments and unknown fields are intentionally ignored.
    flush()
    return events


def _is_terminal(event: GradioEvent) -> bool:
    if event.name in TERMINAL_EVENTS:
        return True
    if isinstance(event.data, Mapping):
        return str(event.data.get("msg") or "").lower() in {
            "process_completed",
            "error",
            "queue_full",
        }
    return False


def _iter_values(value: JsonValue) -> Iterable[JsonValue]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _iter_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_values(child)


def _file_ref_from_value(value: JsonValue, base_url: str) -> GradioFileRef | None:
    if isinstance(value, Mapping):
        candidate_url = value.get("url")
        path = value.get("path")
        name = value.get("orig_name") or value.get("name")
        mime_type = value.get("mime_type")
        if isinstance(candidate_url, str) and candidate_url.strip():
            return GradioFileRef(url=urljoin(base_url.rstrip("/") + "/", candidate_url), name=name, mime_type=mime_type)
        if isinstance(path, str) and path.strip():
            encoded = quote(path.strip(), safe="/")
            return GradioFileRef(
                url=f"{base_url.rstrip('/')}/gradio_api/file={encoded}",
                name=name or Path(path).name,
                mime_type=mime_type,
            )
    if isinstance(value, str) and value.strip():
        candidate = value.strip()
        if candidate.startswith(("http://", "https://", "/")) or candidate.lower().endswith((".mp4", ".webm", ".mov")):
            return GradioFileRef(url=urljoin(base_url.rstrip("/") + "/", candidate), name=Path(candidate).name)
    return None


def find_file_ref(value: JsonValue, base_url: str) -> GradioFileRef | None:
    """Find the first Gradio file-shaped output in a result payload."""

    for candidate in _iter_values(value):
        ref = _file_ref_from_value(candidate, base_url)
        if ref is not None:
            return ref
    return None


def is_mp4_bytes(raw: bytes) -> bool:
    """Apply the project's byte-level MP4 admission signature."""

    return len(raw) >= 8 and raw[4:8] == b"ftyp"


class GradioSpaceClient:
    """Read-only discovery and bounded queue transport for a Gradio Space."""

    def __init__(self, base_url: str, *, timeout: float = 30.0, opener: Opener | None = None) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        self.base_url = normalized
        self.timeout = timeout
        self._opener = opener or urlopen

    def _request(self, method: str, path: str, *, body: JsonValue | None = None, token: str | None = None) -> tuple[int, bytes]:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = _json_bytes(body)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            response = self._opener(request, timeout=self.timeout)
            return _read_response(response)
        except HTTPError as exc:
            status = int(exc.code)
            diagnostic = exc.read(2048).decode("utf-8", errors="replace").strip()
            raise GradioSpaceError(
                f"Gradio {method} {path} returned HTTP {status}: {diagnostic[:500]}",
                status=status,
            ) from exc
        except URLError as exc:
            raise GradioSpaceError(f"Gradio {method} {path} transport failed: {exc.reason}") from exc

    def openapi(self) -> Mapping[str, Any]:
        status, raw = self._request("GET", "/gradio_api/openapi.json")
        if status != 200:
            raise GradioSpaceError(f"Gradio OpenAPI discovery returned HTTP {status}", status=status)
        value = _decode_json(raw, context="OpenAPI discovery")
        if not isinstance(value, Mapping):
            raise GradioSpaceError("Gradio OpenAPI discovery returned a non-object")
        return value

    def info(self) -> Mapping[str, Any]:
        status, raw = self._request("GET", "/gradio_api/info")
        if status != 200:
            raise GradioSpaceError(f"Gradio info discovery returned HTTP {status}", status=status)
        value = _decode_json(raw, context="info discovery")
        if not isinstance(value, Mapping):
            raise GradioSpaceError("Gradio info discovery returned a non-object")
        return value

    def submit(self, api_name: str, data: list[JsonValue], *, token: str | None = None) -> str:
        endpoint = api_name.strip().lstrip("/")
        if not endpoint:
            raise ValueError("api_name must not be empty")
        status, raw = self._request("POST", f"/gradio_api/call/{quote(endpoint, safe='')}", body={"data": data}, token=token)
        if status not in (200, 201, 202):
            raise GradioSpaceError(f"Gradio submit returned HTTP {status}", status=status)
        value = _decode_json(raw, context="submit")
        event_id = value.get("event_id") if isinstance(value, Mapping) else None
        if not isinstance(event_id, str) or not event_id.strip():
            raise GradioSpaceError("Gradio submit returned no event_id")
        return event_id.strip()

    def poll(self, api_name: str, event_id: str, *, token: str | None = None) -> GradioEvent:
        endpoint = api_name.strip().lstrip("/")
        event = quote(event_id.strip(), safe="")
        if not endpoint or not event:
            raise ValueError("api_name and event_id must not be empty")
        status, raw = self._request("GET", f"/gradio_api/call/{quote(endpoint, safe='')}/{event}", token=token)
        if status != 200:
            raise GradioSpaceError(f"Gradio poll returned HTTP {status}", status=status)
        events = _parse_sse(raw)
        terminal = next((item for item in reversed(events) if _is_terminal(item)), None)
        if terminal is None:
            raise GradioSpaceError("Gradio poll closed without a terminal event")
        if terminal.name in {"error", "cancelled"} or (isinstance(terminal.data, Mapping) and str(terminal.data.get("msg") or "").lower() in {"error", "queue_full"}):
            raise GradioSpaceError(f"Gradio job ended with {terminal.name}")
        return terminal

    def submit_and_poll(self, api_name: str, data: list[JsonValue], *, token: str | None = None) -> GradioEvent:
        """Submit one bounded job and consume its queue stream to completion."""

        event_id = self.submit(api_name, data, token=token)
        return self.poll(api_name, event_id, token=token)


__all__ = [
    "GradioEvent",
    "GradioFileRef",
    "GradioSpaceClient",
    "GradioSpaceError",
    "find_file_ref",
    "is_mp4_bytes",
]
