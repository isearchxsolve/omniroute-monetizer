#!/usr/bin/env python3
"""Direct, durable native-Omni audio graduation.

This is deliberately separate from chat and video: binary TTS is only admitted
after audio bytes are recognised; STT/translation are only admitted after a
non-empty text result generated from the returned TTS fixture.  It does not
touch OmniRoute state, provider configuration, or browser/seat infrastructure.

``--apply`` is required for every endpoint request.  ``--confirm-audio-spend``
is additionally required because a cloud TTS/STT request may bill a provider.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
REPORT = STATE / "audio_provider_probe.json"
ADMISSIONS = STATE / "omniroute_verified_audio_routes.json"
OMNI = "http://127.0.0.1:20128"
SPEECH_TEXT = "OmniRoute audio verification number four one seven nine."
SPANISH_TEXT = "Hola. La verificacion de audio de OmniRoute esta lista."

# The active 3.8.50 audio registry's OpenAI-compatible endpoints support these
# provider/model forms.  The zero-auth rows establish endpoint wiring without
# relying on an account; account-backed rows are then concrete full E2E probes.
SPEECH_DEFAULTS = ["gtts/default", "edgetts/en-US-AriaNeural", "openai/tts-1"]
TRANSCRIBE_DEFAULTS = ["openai/whisper-1", "groq/whisper-large-v3"]
TRANSLATE_DEFAULTS = ["openai/whisper-1", "groq/whisper-large-v3"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def no_proxy_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def audio_signature(data: bytes) -> str | None:
    """Recognise common real-audio containers without trusting HTTP 200 alone."""
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"ID3") or (len(data) > 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "m4a/mp4"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return None
    return None


def redacted_body(text: str) -> str:
    # Native audio failures are metadata, but avoid retaining a potentially
    # forwarded credential URL or arbitrarily large response.
    return text.replace("?", "?[REDACTED]")[:500]


def extract_text(payload: Any, raw: str) -> str:
    if isinstance(payload, dict):
        for key in ("text", "transcript", "translation"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return raw.strip()


def speech_probe(session: requests.Session, model: str, text: str, voice: str, timeout: float) -> tuple[dict[str, Any], bytes]:
    started = dt.datetime.now(dt.timezone.utc)
    result: dict[str, Any] = {"modality": "speech", "model": model, "state": "NOT_PROVEN"}
    try:
        response = session.post(f"{OMNI}/v1/audio/speech", json={
            "model": model, "input": text, "voice": voice, "response_format": "mp3",
        }, headers={"Content-Type": "application/json"}, timeout=timeout)
        data = response.content
        kind = audio_signature(data)
        result.update(http=response.status_code, contentType=response.headers.get("Content-Type"),
                      bytes=len(data), audioFormat=kind,
                      sha256=hashlib.sha256(data).hexdigest() if kind else None,
                      state="SPEECH_BYTES_OK" if response.status_code == 200 and kind and len(data) >= 128
                      else "SPEECH_NOT_AUDIO")
        if result["state"] != "SPEECH_BYTES_OK":
            result["error"] = redacted_body(response.text)
        return result, data if result["state"] == "SPEECH_BYTES_OK" else b""
    except Exception as exc:
        result.update(state="TRANSPORT", error=f"{type(exc).__name__}: {exc}"[:300])
        return result, b""
    finally:
        result["verifiedAt"] = now()
        result["latencyMs"] = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)


def translation_looks_english(text: str) -> bool:
    """The Spanish fixture must come back as English, not merely as text."""
    normalized = " ".join(text.lower().split())
    return "verification" in normalized and "verificacion" not in normalized


def text_probe(session: requests.Session, endpoint: str, modality: str, model: str, audio: bytes,
               timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {"modality": modality, "model": model, "state": "NOT_PROVEN"}
    try:
        files = {"file": ("omniroute-audio-proof.mp3", audio, "audio/mpeg")}
        response = session.post(f"{OMNI}{endpoint}", data={"model": model, "response_format": "json"},
                                files=files, timeout=timeout)
        try:
            body: Any = response.json()
        except ValueError:
            body = {}
        text = extract_text(body, response.text)
        valid_text = response.status_code == 200 and len(text) >= 3
        if modality == "translation":
            valid_text = valid_text and translation_looks_english(text)
        result.update(http=response.status_code, text=text[:300], textSha256=hashlib.sha256(text.encode()).hexdigest(),
                      state=f"{modality.upper()}_TEXT_OK" if valid_text else f"{modality.upper()}_NO_TEXT")
        if result["state"].endswith("NO_TEXT"):
            result["error"] = redacted_body(response.text)
    except Exception as exc:
        result.update(state="TRANSPORT", error=f"{type(exc).__name__}: {exc}"[:300])
    result["verifiedAt"] = now()
    return result


def admission_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted = {"SPEECH_BYTES_OK", "TRANSCRIPTION_TEXT_OK", "TRANSLATION_TEXT_OK"}
    return [{"model": r["model"], "modality": r["modality"], "state": "ADMITTED",
             "proof": r["state"], "verifiedAt": r["verifiedAt"]}
            for r in results if r.get("state") in accepted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="write the explicit no-request audio plan")
    parser.add_argument("--apply", action="store_true", help="required before direct Omni audio requests")
    parser.add_argument("--confirm-audio-spend", action="store_true", help="required with --apply")
    parser.add_argument("--speech", action="store_true", help="run TTS proof candidates")
    parser.add_argument("--transcription", action="store_true", help="transcribe returned TTS bytes")
    parser.add_argument("--translation", action="store_true", help="translate returned TTS bytes to English")
    parser.add_argument("--model", action="append", default=[], help="override candidates; repeatable")
    parser.add_argument("--timeout", type=float, default=90, help="one direct endpoint timeout")
    args = parser.parse_args()
    selected = {"speech": SPEECH_DEFAULTS, "transcription": TRANSCRIBE_DEFAULTS,
                "translation": TRANSLATE_DEFAULTS}
    if args.model:
        # Explicit models are used only for the requested modality, retaining a
        # deterministic record of operator-directed expansion candidates.
        for key in selected:
            if getattr(args, key): selected[key] = list(dict.fromkeys(args.model))
    requested = [k for k in selected if getattr(args, k)] or ["speech", "transcription", "translation"]
    plan = {"schemaVersion": 1, "generatedAt": now(), "endpoint": OMNI,
            "contracts": {"speech": "/v1/audio/speech", "transcription": "/v1/audio/transcriptions",
                          "translation": "/v1/audio/translations"},
            "requested": requested, "candidates": {k: selected[k] for k in requested},
            "proofRules": {"speech": "HTTP 200 + >=128 bytes + recognized audio container",
                           "transcription": "HTTP 200 + non-empty transcript from returned speech bytes",
                           "translation": "HTTP 200 + non-empty English translation from returned speech bytes"}}
    if args.plan or not args.apply:
        atomic_json(STATE / "audio_probe_plan.json", plan)
        print(json.dumps({"state": "PLAN_ONLY", "requested": requested,
                          "candidateCounts": {k: len(selected[k]) for k in requested}}))
        return 0
    if not args.confirm_audio_spend:
        parser.error("--apply requires --confirm-audio-spend")
    session = no_proxy_session()
    results: list[dict[str, Any]] = []
    fixture = b""
    # A speech response is deliberately used as the STT/translation fixture.
    # It prevents an endpoint 200 over a silent/tone fixture from manufacturing
    # text capacity and keeps the whole proof direct through OmniRoute.
    for model in selected["speech"] if "speech" in requested or any(k in requested for k in ("transcription", "translation")) else []:
        row, data = speech_probe(session, model, SPEECH_TEXT, "alloy", args.timeout)
        results.append(row)
        if data and not fixture:
            fixture = data
    if "transcription" in requested:
        if not fixture:
            results.append({"modality": "transcription", "model": "<no-speech-fixture>",
                            "state": "SKIPPED_NO_VERIFIED_SPEECH_FIXTURE", "verifiedAt": now()})
        else:
            for model in selected["transcription"]:
                results.append(text_probe(session, "/v1/audio/transcriptions", "transcription", model, fixture, args.timeout))
    if "translation" in requested:
        # Translation needs an actual non-English source. gTTS exposes its
        # language as the OpenAI-shaped voice field, so this is a direct Omni
        # Spanish-TTS -> multipart-translation proof rather than an English
        # transcription accidentally passing as a translation.
        spanish_row, spanish_fixture = speech_probe(session, "gtts/default", SPANISH_TEXT, "es", args.timeout)
        spanish_row["proofPurpose"] = "translation_fixture"
        results.append(spanish_row)
        if not spanish_fixture:
            results.append({"modality": "translation", "model": "<no-speech-fixture>",
                            "state": "SKIPPED_NO_VERIFIED_SPEECH_FIXTURE", "verifiedAt": now()})
        else:
            for model in selected["translation"]:
                results.append(text_probe(session, "/v1/audio/translations", "translation", model, spanish_fixture, args.timeout))
    report = {**plan, "state": "COMPLETE", "completedAt": now(), "results": results}
    atomic_json(REPORT, report)
    atomic_json(ADMISSIONS, {"schemaVersion": 1, "generatedAt": now(), "endpoint": OMNI,
                              "entries": admission_rows(results)})
    print(json.dumps({"state": "COMPLETE", "results": len(results), "admitted": len(admission_rows(results))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
