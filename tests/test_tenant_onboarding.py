from pathlib import Path

from scripts.automation.tenant_onboarding import (
    generate_key,
    load_map,
    redact,
    write_map_atomic,
)


def test_generated_keys_are_prefixed_and_unique() -> None:
    keys = {generate_key() for _ in range(50)}
    assert len(keys) == 50
    assert all(k.startswith("sk-omni-") for k in keys)
    assert all(len(k) > 20 for k in keys)


def test_map_roundtrip_is_atomic_and_loadable(tmp_path: Path) -> None:
    target = tmp_path / "tenant_map.json"
    mapping = {"sk-omni-abc": "tenant_001", "sk-omni-def": "tenant_002"}
    write_map_atomic(target, mapping)
    assert target.exists()
    assert not target.with_suffix(".json.tmp").exists()
    assert load_map(target) == mapping


def test_missing_map_means_open_gate(tmp_path: Path) -> None:
    assert load_map(tmp_path / "absent.json") == {}


def test_redaction_never_reveals_full_key() -> None:
    key = generate_key()
    shown = redact(key)
    assert shown.startswith("sk-omni-")
    assert shown.endswith("...")
    assert shown not in key or len(shown) < len(key)
    assert len(shown) == 15
