#!/usr/bin/env python3
"""Sanitize state/full_e2e_automation_report.json: mask all plaintext API keys
in-place (T11 / DPAPI-vault mandate). Keeps structure, replaces secret values
with masked forms. Never prints secret values.
"""
import json
import re
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "state" / "full_e2e_automation_report.json"

KEY_PATTERNS = [
    (re.compile(r"sk-or-v1-[0-9a-fA-F]{20,}"), "sk-or-v1-[REDACTED]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "sk-ant-[REDACTED]"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_[REDACTED]"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "gho_[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-[REDACTED]"),
    (re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"), "nvapi-[REDACTED]"),
]


def mask_value(v: str) -> str:
    for pat, repl in KEY_PATTERNS:
        v = pat.sub(repl, v)
    return v


def walk(obj):
    if isinstance(obj, dict):
        return {k: walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v) for v in obj]
    if isinstance(obj, str):
        return mask_value(obj)
    return obj


def main() -> int:
    data = json.loads(TARGET.read_text(encoding="utf-8"))
    cleaned = walk(data)
    TARGET.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    # verify no patterns remain
    text = TARGET.read_text(encoding="utf-8")
    remaining = sum(len(pat.findall(text)) for pat, _ in KEY_PATTERNS)
    print(f"[+] sanitized {TARGET.name}; remaining key-like strings: {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
