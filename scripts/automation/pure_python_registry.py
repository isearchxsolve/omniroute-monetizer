"""Exact-file admission registry for browser-independent pool seats.

``state/replay_check.json`` is intentionally host-level: it answers whether at
least one capture for a host passed the Law-3 probe.  That is useful for the
legacy chat pool, but it is not enough to promote a *specific* browser seat:
the same host can have multiple account/session files.  This module is the
small, secret-free bridge between a per-file proof and the hot-reloading
``session_pool`` on :8190.

The registry contains only filenames, hosts, modalities, adapter names, and
proof metadata.  Cookie values, request bodies, headers, and URLs with query
parameters remain in ``state/secrets/`` and are never copied here.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
REGISTRY = STATE / "pure_python_replay_registry.json"

PURE_PYTHON_API_KINDS = frozenset({
    "aistudio", "digen", "kie", "omniroute_native", "rtst", "youcom",
})


def load_registry(path: pathlib.Path = REGISTRY) -> dict[str, Any]:
    """Return a validated, non-secret registry shape; malformed files fail closed."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    entries = raw.get("entries") if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        entries = []
    return {
        "schemaVersion": 1,
        "generatedAt": str(raw.get("generatedAt") or "") if isinstance(raw, dict) else "",
        "entries": [e for e in entries if isinstance(e, dict)],
    }


def write_registry(registry: dict[str, Any], path: pathlib.Path = REGISTRY) -> None:
    """Atomically publish non-secret admission metadata for the shim hot-reload."""
    clean = {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entries": list(registry.get("entries") or []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def admitted_chat_session_keys(path: pathlib.Path = REGISTRY) -> set[str]:
    """Exact session-file stems admitted after a per-file Law-3 verification."""
    out: set[str] = set()
    for entry in load_registry(path)["entries"]:
        filename = str(entry.get("sessionFile") or "")
        if (entry.get("state") == "ADMITTED" and entry.get("modality") == "chat"
                and filename.startswith("session_") and filename.endswith(".json")):
            out.add(pathlib.Path(filename).stem)
    return out


def transport_for(raw: dict[str, Any]) -> str:
    if raw.get("recorded_ws") or raw.get("transport") == "websocket":
        return "websocket"
    if raw.get("recorded_job"):
        return "video-job"
    if raw.get("recorded_exchange"):
        return "http"
    if isinstance(raw.get("api"), dict) and raw["api"].get("kind"):
        return "api"
    return "none"


def pure_python_adapter(raw: dict[str, Any]) -> str | None:
    """Name the adapter that SessionPool can invoke without Chrome at request time."""
    api = raw.get("api") if isinstance(raw.get("api"), dict) else {}
    kind = str(api.get("kind") or "")
    if kind in PURE_PYTHON_API_KINDS:
        return f"api:{kind}"
    transport = transport_for(raw)
    if transport == "websocket":
        return "ws_replay.WebSocketSessionClient"
    if transport == "video-job" or raw.get("modality") == "video":
        return "video_universal_replay.VideoUniversalSessionClient"
    if transport == "http":
        return "universal_replay.UniversalSessionClient"
    return None


def admission_problem(raw: dict[str, Any]) -> str | None:
    """Fail-closed eligibility check.  This is structure, not proof of health."""
    if not isinstance(raw, dict) or not str(raw.get("host") or ""):
        return "missing host"
    if raw.get("chrome"):
        return "Chrome-backed runtime is not a pure-Python admission"
    if pure_python_adapter(raw) is None:
        return "no registered pure-Python adapter or recorded transport"
    return None


def admit(registry: dict[str, Any], *, session_file: str, host: str, modality: str,
          adapter: str, verification: dict[str, Any]) -> dict[str, Any]:
    """Upsert one exact-file admission; return the new non-secret entry."""
    if not session_file.startswith("session_") or not session_file.endswith(".json"):
        raise ValueError("session_file must be a session_*.json filename")
    if modality not in {"chat", "video"}:
        raise ValueError("modality must be chat or video")
    entry = {
        "sessionFile": session_file,
        "host": host,
        "modality": modality,
        "adapter": adapter,
        "state": "ADMITTED",
        "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verification": verification,
    }
    entries = [e for e in registry.get("entries") or []
               if isinstance(e, dict) and e.get("sessionFile") != session_file]
    entries.append(entry)
    registry["entries"] = entries
    return entry
