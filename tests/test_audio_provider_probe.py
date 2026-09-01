import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "automation" / "audio_provider_probe.py"
SPEC = importlib.util.spec_from_file_location("audio_provider_probe", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_audio_signature_recognises_real_containers_and_rejects_html():
    assert MOD.audio_signature(b"RIFFxxxxWAVE" + b"x" * 200) == "wav"
    assert MOD.audio_signature(b"OggS" + b"x" * 200) == "ogg"
    assert MOD.audio_signature(b"ID3" + b"x" * 200) == "mp3"
    assert MOD.audio_signature(b"<!doctype html>" + b"x" * 200) is None


def test_extract_text_requires_a_real_text_field_or_plain_text():
    assert MOD.extract_text({"text": "verified speech"}, "") == "verified speech"
    assert MOD.extract_text({}, " verified translation ") == "verified translation"


def test_translation_requires_english_semantics_from_the_spanish_fixture():
    assert MOD.translation_looks_english("OmniRoute audio verification is ready")
    assert not MOD.translation_looks_english("La verificacion de audio esta lista")


def test_admission_rows_only_admits_modality_specific_proofs():
    rows = MOD.admission_rows([
        {"model": "gtts/default", "modality": "speech", "state": "SPEECH_BYTES_OK", "verifiedAt": "now"},
        {"model": "openai/whisper-1", "modality": "transcription", "state": "TRANSCRIPTION_NO_TEXT", "verifiedAt": "now"},
    ])
    assert rows == [{"model": "gtts/default", "modality": "speech", "state": "ADMITTED",
                     "proof": "SPEECH_BYTES_OK", "verifiedAt": "now"}]


def test_admission_rows_deduplicates_a_translation_fixture_speech_route():
    rows = MOD.admission_rows([
        {"model": "gtts/default", "modality": "speech", "state": "SPEECH_BYTES_OK", "verifiedAt": "one"},
        {"model": "gtts/default", "modality": "speech", "state": "SPEECH_BYTES_OK", "verifiedAt": "two"},
    ])
    assert len(rows) == 1
    assert rows[0]["verifiedAt"] == "two"
