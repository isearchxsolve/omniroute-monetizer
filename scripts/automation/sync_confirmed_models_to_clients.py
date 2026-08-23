#!/usr/bin/env python3
"""Sync confirmed healthy model routes into the Codex client profiles."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "state" / "healthy_provider_models_rescan.json"
PROFILE_JSON = Path(__file__).resolve().parent / "98e83bfd-e627-4557-a52e-9dcc8a008f50.json"
CODEX_YAML = Path(__file__).resolve().parent / "codex omni.yml"
ZCODE_JSON = Path.home() / ".zcode" / "v2" / "config.json"

PROVIDER_ORDER = {
    "codex": 0, "anthropic": 1, "ainative": 2, "openrouter": 3,
    "alibaba": 4, "gemini": 5, "kimi-coding": 6, "kiro": 7,
    "kilocode": 8, "nvidia": 9, "mistral": 10, "deepinfra": 11,
    "requesty": 12, "opencode-zen": 13, "chatgpt-web": 14,
    "perplexity-web": 15, "gemini-web": 16, "reka": 17,
    "openadapter": 18, "agentrouter": 19, "groq": 20, "cerebras": 21,
}
POWER_TERMS = (
    (0, ("opus", "gpt-5.6-sol", "gpt-5.6-pro", "gpt-5.6")),
    (1, ("sonnet", "gpt-5.5", "gpt-5.4", "deepseek-v4", "qwen3.7-max")),
    (2, ("deepseek", "qwen", "grok", "gemini-3.7", "gemini-3.6")),
    (3, ("coder", "codestral", "devstral", "reason", "think")),
    (4, ("flash", "large", "medium", "pro")),
)


def power_key(route: str) -> tuple[int, int, int, str]:
    provider, _, model = route.partition("/")
    lowered = model.lower()
    term_rank = next((rank for rank, terms in POWER_TERMS if any(term in lowered for term in terms)), 5)
    return (PROVIDER_ORDER.get(provider, 99), term_rank, len(route), route.lower())


def confirmed_routes() -> list[str]:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    routes = {
        f"{row['provider']}/{row['model']}"
        for row in report["results"]
        if row.get("valid") and row.get("provider") and row.get("model")
    }
    return sorted(routes, key=power_key)


def sync_json(routes: list[str]) -> None:
    data = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
    existing = data.get("inferenceModels", [])
    labels = {item.get("name"): item.get("labelOverride") for item in existing}
    data["inferenceModels"] = [
        {
            "name": route,
            "labelOverride": labels.get(route, f"OmniRoute confirmed: {route}"),
            "isFamilyDefault": index == 0,
        }
        for index, route in enumerate(routes)
    ]
    PROFILE_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sync_codex(routes: list[str]) -> None:
    text = CODEX_YAML.read_text(encoding="utf-8")
    start_marker = "[tui.model_availability_nux]"
    end_marker = "\n\n# ------------------------------------------------------------\n# PROJECT TRUST"
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    availability = "\n".join(f'"{route}" = 4' for route in routes)
    replacement = f"{start_marker}\n{availability}"
    CODEX_YAML.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def sync_zcode(routes: list[str]) -> None:
    if not ZCODE_JSON.exists():
        print(f"zcode=missing:{ZCODE_JSON}")
        return
    data = json.loads(ZCODE_JSON.read_text(encoding="utf-8"))
    provider = data.setdefault("provider", {}).setdefault("custom:omniroute", {})
    old_models = provider.get("models") or {}
    models = {}
    for priority, route in enumerate(routes, start=1):
        old = old_models.get(route) or {}
        models[route] = {
            "name": route,
            "displayName": old.get("displayName", f"OmniRoute confirmed: {route}"),
            "limit": old.get("limit", {"context": 200000, "output": 32000}),
            "modalities": old.get("modalities", {"input": ["text"], "output": ["text"]}),
            "zcode": {**(old.get("zcode") or {}), "modified": False, "priority": priority},
        }
    provider["models"] = models
    ZCODE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"zcode={ZCODE_JSON}")


def main() -> None:
    routes = confirmed_routes()
    sync_json(routes)
    sync_codex(routes)
    sync_zcode(routes)
    print(f"synced_confirmed_routes={len(routes)}")
    print(f"json={PROFILE_JSON}")
    print(f"yaml={CODEX_YAML}")


if __name__ == "__main__":
    main()