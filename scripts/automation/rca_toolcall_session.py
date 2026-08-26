#!/usr/bin/env python3
"""RCA for the 2026-08-26 session where every Claude Code tool call failed.

Symptom, verbatim, ~40 times in a row:

    Error: No such tool available: read
    Error: No such tool available: bash
    Error: No such tool available: glob

The client registers `Read`, `Bash`, `Glob`. The config in play pointed at the :20130 superset
gateway with 18 entries and `isFamilyDefault: false` on every single one of them, so which route
served the session was never pinned.

probe_tool_fidelity.py already caught a near-identical failure on 2026-08-25 and scored five routes
`tools_ok`. Two things about that verdict need testing before it can be trusted for a real session:

  1. it sends 14 tools; a real Claude Code session with this repo's MCP servers attached sends ~45,
     with far longer schemas and a much longer system prompt. If a route drops or truncates the
     tools array once the request gets big, the model still reads in the system prompt that it
     ought to be calling tools, so it invents one from habit -- and an invented shell tool gets
     written `bash`, an invented file reader `read`. Exactly the two names that failed.

  2. it never probed a single `pool/*` seat (state/tool_fidelity.json: POOL SEATS PROBED: NONE).
     Those seats are browser-replay sessions against free consumer chat UIs. They are text in,
     text out. They cannot emit a tool_use block at all. And :20130 falls back to them silently
     whenever an upstream route refuses -- which 7 of the 12 non-pool routes in that config do.

So this script asks three questions, one request each, serial, nothing retried or hammered:

    A  does a pool/* seat return a tool_use block when handed a tools array?
    B  does a route that 404s upstream fall back to a pool seat and answer anyway?  <- the trap
    C  does a route probe_tool_fidelity blessed still return an exact `Bash` at real-client scale?

Read-only with respect to service lifecycle: this POSTs to :20130 and nothing else. It never starts,
stops or reconfigures :20128, which is not ours.

Usage:
    python rca_toolcall_session.py
    python rca_toolcall_session.py --tools 45     # payload size under test
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Any

import requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATEWAY = "http://127.0.0.1:20130"
OUT = ROOT / "state" / "rca_toolcall_session.json"
TIMEOUT = 90

# Capitalised on purpose. That capital B is the whole experiment.
TOOL_NAME = "Bash"

# The names a real session has attached, MCP servers included. Used to pad the tools array to
# real-client size, because size is the variable probe_tool_fidelity.py did not push hard enough.
REAL_TOOL_NAMES = [
    "Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch",
    "Agent", "AskUserQuestion", "EnterPlanMode", "ExitPlanMode", "EnterWorktree", "ExitWorktree",
    "TaskOutput", "TaskStop", "Skill", "SendMessage", "SendUserFile", "Workflow", "DesignSync",
    "CronCreate", "CronList", "CronDelete", "ScheduleWakeup", "ReportFindings",
    "mcp__ccd_directory__change_directory", "mcp__ccd_directory__request_directory",
    "mcp__ccd_session__spawn_task", "mcp__ccd_session__dismiss_task",
    "mcp__ccd_session__mark_chapter", "mcp__ccd_session__read_widget_context",
    "mcp__ccd_session_mgmt__list_sessions", "mcp__ccd_session_mgmt__get_session",
    "mcp__ccd_session_mgmt__list_events", "mcp__ccd_session_mgmt__send_message",
    "mcp__Claude_Browser__preview_start", "mcp__Claude_Browser__preview_click",
    "mcp__Claude_Browser__preview_fill", "mcp__Claude_Browser__preview_eval",
    "mcp__Claude_Browser__preview_snapshot", "mcp__Claude_Browser__preview_inspect",
    "mcp__Claude_Browser__preview_screenshot", "mcp__Claude_Browser__preview_console_logs",
    "mcp__scheduled-tasks__create_scheduled_task", "mcp__terminal__read_terminal",
]

# Must never contain the tool's name -- otherwise a route that lowercases from habit still passes by
# copying the capital B out of the prompt.
PROMPT = ("Run the shell command `echo hi` and report its output. You have a tool available for "
          "running shell commands -- use it. Do not answer in prose.")

SYSTEM = ("You are an interactive CLI tool that helps users with software engineering tasks. "
          "Use the available tools to inspect and modify the codebase. Prefer the dedicated file "
          "and search tools over shell commands when one fits. Never guess at file contents -- "
          "read the file. " * 60)

CASES = [
    ("A_pool_seat", "pool/claude-sonnet-4-6",
     "a pool seat is a scraped chat UI; can it emit tool_use at all?"),
    ("B_dead_upstream_fallback", "anthropic/claude-sonnet-4-6",
     "404s on :20128 per tool_fidelity.json -- does :20130 fall back to the pool and answer anyway?"),
    ("C_blessed_route_at_scale", "agy/claude-sonnet-4-6",
     "scored tools_ok at 14 tools; does it hold at real-client scale?"),
]


def build_tools(count: int) -> list[dict[str, Any]]:
    """Bash keeps its real schema so the verdict stays comparable to probe_tool_fidelity.py; the
    rest exist to push the payload to the size a real session actually sends."""
    tools = [{
        "name": TOOL_NAME,
        "description": "Run a shell command and return its stdout.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The command to run"}},
            "required": ["command"],
        },
    }]
    for name in REAL_TOOL_NAMES:
        if name == TOOL_NAME or len(tools) >= count:
            continue
        tools.append({
            "name": name,
            "description": (f"The {name} tool. Use it when the task calls for {name}. " * 10).strip(),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to operate on"},
                    "pattern": {"type": "string", "description": "Pattern to match against"},
                    "content": {"type": "string", "description": "Content to write out"},
                },
                "required": [],
            },
        })
    return tools


def tool_names(body: dict) -> list[str]:
    """Every name this response tried to call, across both wire shapes. A pool seat answering
    OpenAI-shaped on an Anthropic endpoint is itself a fidelity problem worth recording."""
    names: list[str] = []
    content = body.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                names.append(str(block.get("name") or ""))
    try:
        msg = (body.get("choices") or [{}])[0].get("message") or {}
        for call in (msg.get("tool_calls") or []):
            fn = (call or {}).get("function") or {}
            if fn.get("name"):
                names.append(str(fn["name"]))
    except (AttributeError, IndexError, TypeError):
        pass
    return [n for n in names if n]


def prose(body: dict) -> str:
    content = body.get("content")
    if isinstance(content, list):
        joined = "".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
        if joined.strip():
            return joined.strip()
    try:
        return str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    except (AttributeError, IndexError, TypeError):
        return ""


def run_case(label: str, model: str, why: str, tools: list[dict]) -> dict[str, Any]:
    row: dict[str, Any] = {"case": label, "model": model, "question": why,
                           "toolsSent": len(tools)}
    payload = {"model": model, "max_tokens": 256, "system": SYSTEM,
               "tools": tools, "messages": [{"role": "user", "content": PROMPT}]}
    row["requestBytes"] = len(json.dumps(payload))
    started = time.perf_counter()
    try:
        r = requests.post(f"{GATEWAY}/v1/messages", json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:
        row.update(verdict="error", toolSafe=False, errorType=type(e).__name__,
                   latencyMs=round((time.perf_counter() - started) * 1000))
        return row
    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
    row["httpStatus"] = r.status_code
    try:
        body = r.json()
    except ValueError:
        row.update(verdict="empty", toolSafe=False, bodyHead=(r.text or "")[:300])
        return row

    # Which member actually answered. This is the field the whole RCA turns on: a fallback means
    # the model the client asked for is not the model that replied.
    for key in ("model", "servedBy", "provider", "route", "_omni_route", "x_route"):
        if isinstance(body.get(key), str):
            row.setdefault("servedBy", body[key])
            break

    names = tool_names(body)
    row["toolNamesReturned"] = names
    if r.status_code != 200:
        row.update(verdict="not_routed" if r.status_code == 404 else "error", toolSafe=False,
                   detail=str(body.get("error") or body.get("detail") or "")[:300])
    elif not names:
        row.update(verdict="no_tool_use", toolSafe=False, prose=prose(body)[:400])
    elif TOOL_NAME in names:
        row.update(verdict="tools_ok", toolSafe=True)
    else:
        row.update(verdict="tools_mangled", toolSafe=False, prose=prose(body)[:200])
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", type=int, default=45,
                    help="payload size under test; a real session sends about 45")
    args = ap.parse_args()

    tools = build_tools(args.tools)
    print(f"gateway {GATEWAY}  tools={len(tools)}  "
          f"payload={len(json.dumps({'tools': tools, 'system': SYSTEM}))} bytes\n")

    rows = []
    for label, model, why in CASES:
        print(f"[{time.strftime('%H:%M:%S')}] {label:26s} {model}")
        row = run_case(label, model, why, tools)
        rows.append(row)
        served = f"  servedBy={row['servedBy']}" if row.get("servedBy") else ""
        print(f"    -> {row['verdict']:14s} safe={row.get('toolSafe')}  "
              f"names={row.get('toolNamesReturned')}{served}")
        if row.get("prose"):
            print(f"       prose: {row['prose'][:160]!r}")
        if row.get("detail"):
            print(f"       detail: {row['detail'][:160]}")
        time.sleep(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "gateway": GATEWAY,
        "toolsSent": len(tools),
        "toolNameUnderTest": TOOL_NAME,
        "symptom": "Claude Code reported 'No such tool available: read/bash/glob' for an entire session",
        "results": rows,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
