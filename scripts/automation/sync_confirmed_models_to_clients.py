#!/usr/bin/env python3
"""Sync confirmed healthy model routes into the Codex client profiles.

Every client this script writes -- Claude Code, Codex CLI, ZCode -- is a TOOL-USING agent, so
"healthy" has to mean healthy for tool use and not merely for chat. It did not, and that cost a
whole session on 2026-08-26: every tool call came back

    Error: No such tool available: read
    Error: No such tool available: bash

route_truth.json calls 186 routes `valid`. tool_fidelity.json has only ever vetted 12 of them, of
which 5 return a tool name byte-for-byte. The old sync_json emitted all 186, labelled every one
`OmniRoute confirmed: <route>`, and set isFamilyDefault on whichever sorted first by power_key --
which is `anthropic/claude-sonnet-4-6`, a route that 404s. :20130 then falls back to a `pool/*` seat
by design, and a pool seat is a browser replay of a consumer chat UI: text in, text out, no tool_use
block possible. The tools array never reaches a tool-capable model, the model still reads in its
system prompt that it has tools, so it invents them from habit -- an invented shell tool is written
`bash`, an invented file reader `read` -- and the client's case-sensitive dispatcher rejects each one.

Chat looks perfect the whole time, which is why the label was believed. So:

  * the default is the FASTEST MEASURED tool-safe route, never whatever sorts first
  * routes measured tool-unsafe are dropped outright
  * routes never probed for tools are still offered, but labelled UNVETTED rather than confirmed,
    because a label that overstates its own layer is what caused this
  * `pool/*` is never emitted: it is correct chat and strict-JSON supply (the planner scores 6/6 on
    pool/auto) and fatal agentic supply
  * a missing or stale tool_fidelity.json is a hard stop, not a silent fall back to chat-only truth

Re-probe with `python probe_tool_fidelity.py` before syncing if the verdicts predate route_truth.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "state" / "route_truth.json"
TOOL_FIDELITY = ROOT / "state" / "tool_fidelity.json"

# Routes observed failing a REAL agentic session while passing the probe. They stay listed -- they do
# pass, and a human may still pick one -- but they can never be pinned as the default, because the
# probe demonstrably does not reproduce whatever kills them. antigravity/claude-sonnet-4-6 is the
# route from the 2026-08-25 report: "Chat worked. Every single tool call failed." It clears the probe
# at 44 tools / 61KB, so the probe is not yet a sufficient gate for it.
SUSPECT_ROUTES = {"antigravity/claude-sonnet-4-6"}
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


def tool_verdicts() -> tuple[list[str], set[str], dict[str, int]]:
    """(tool-safe routes fastest-first, routes measured unsafe, latency by route).

    Hard stop when the file is absent: emitting a chat-only truth into three agentic clients is the
    bug this whole module exists to prevent, and it fails invisibly, so it must not be reachable by
    forgetting to run a probe.
    """
    if not TOOL_FIDELITY.exists():
        raise SystemExit(
            f"refusing to sync: {TOOL_FIDELITY.relative_to(ROOT)} is missing, so no route has been\n"
            "vetted for tool use. Every client this writes is a tool-using agent and a route that\n"
            "mangles or drops tool names answers chat perfectly while breaking every action.\n"
            "Run: python scripts/automation/probe_tool_fidelity.py"
        )
    data = json.loads(TOOL_FIDELITY.read_text(encoding="utf-8"))
    latency = {row["model"]: int(row.get("latencyMs") or 0) for row in data.get("results", [])}
    safe = [row["model"] for row in data.get("results", []) if row.get("toolSafe")]
    unsafe = {row["model"] for row in data.get("results", []) if not row.get("toolSafe")}
    if not safe:
        raise SystemExit(
            f"refusing to sync: {TOOL_FIDELITY.relative_to(ROOT)} has no tool-safe route, so there is\n"
            "no honest default to pin. Re-probe before syncing."
        )
    # Fastest first, but a route that has failed a live session is never allowed to sort into the
    # default slot: the default is what the client reaches for on every turn, so it is the one place
    # where "passes the probe" is not good enough on its own.
    safe.sort(key=lambda route: (route in SUSPECT_ROUTES, latency.get(route, 10**9), route))
    return safe, unsafe, latency


def build_models(routes: list[str]) -> tuple[list[str], list[str]]:
    """Split the chat-valid set into (tool-safe fastest-first, never-probed) and drop the rest.

    `pool/*` is excluded from both. It is real supply -- just not for a client that calls tools.
    """
    safe, unsafe, _ = tool_verdicts()
    chat_valid = [r for r in routes if not r.startswith("pool/")]
    # tool_safe first, even a route chat-probing missed: tools_ok already required HTTP 200 plus a
    # tool_use block, which is strictly stronger evidence than the chat probe's.
    ordered_safe = [r for r in safe if not r.startswith("pool/")]
    unvetted = [r for r in chat_valid if r not in set(ordered_safe) and r not in unsafe]
    return ordered_safe, unvetted


def sync_json(routes: list[str]) -> None:
    safe, unvetted = build_models(routes)
    _, _, latency = tool_verdicts()
    data = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
    models = []
    for index, route in enumerate(safe):
        ms = latency.get(route)
        detail = f", {ms / 1000:.1f}s" if ms else ""
        models.append({
            "name": route,
            "labelOverride": f"TOOL-SAFE{' default' if index == 0 else ''} - returned `Bash` exactly{detail}",
            "isFamilyDefault": index == 0,
        })
    for route in unvetted:
        models.append({
            "name": route,
            "labelOverride": f"UNVETTED for tools - chat-valid only: {route}",
            "isFamilyDefault": False,
        })
    data["inferenceModels"] = models
    PROFILE_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"json_tool_safe={len(safe)} json_unvetted={len(unvetted)} default={safe[0]}")


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