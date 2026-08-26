#!/usr/bin/env python3
"""Probe whether a route can be trusted with TOOL USE, not just with chat.

Why this exists, measured 2026-08-25:

Claude Code was pointed at OmniRoute on `antigravity/claude-sonnet-4-6`. Chat worked. Every single
tool call failed with:

    Error: No such tool available: read
    Error: No such tool available: bash

The harness registers its tools as `Read` and `Bash` -- capitalised. The names came back from that
route LOWERCASED, so every dispatch missed the registry and the agent was left unable to read a
file or run a command for an entire session. Switching to `agentrouter/claude-opus-5` fixed it on
the first call.

That is a failure mode `probe_route_truth.py` cannot see. It sends a plain prompt and scores the
reply, so a route that mangles function-call names still scores `ok` -- correctly, for chat. But the
clients this repo actually feeds (Claude Code, ZCode, Zed, Codex CLI) are all tool-using agents, and
for them a name-mangling route is worse than a dead one: a dead route fails fast and fails over,
while this one answers confidently and then breaks every action the agent tries to take.

So this probe asks the one question that matters for an agentic client: if I hand you a tool called
exactly `Bash`, do you call it back by exactly that name?

    tools_ok        tool_use block returned, name matched byte for byte  -> safe for Claude Code
    tools_mangled   tool_use block returned, name differs (case/shape)   -> UNSAFE, records what it sent
    no_tool_use     answered in prose instead of calling the tool        -> weak; may be prompt-shy
    empty           HTTP 200, nothing usable in the body
    not_routed      404: gateway refuses the id
    auth / wall / rate / error

`tools_mangled` is the verdict worth the whole script. It is invisible to every other probe here.

One request per route, serial, 60s ceiling. Nine routes takes about a minute. Nothing is retried
and nothing is hammered: a wall or a rate limit is recorded and the route is left alone.

No key, token or cookie is read or printed by this script.

Usage:
    python probe_tool_fidelity.py                      # the routes in the oioi config
    python probe_tool_fidelity.py --models a/b,c/d     # just these
    python probe_tool_fidelity.py --config path.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import time
from typing import Any

import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]

BASE = "http://127.0.0.1:20128"
CONFIG = HERE / "98e83bfd-e627-4557-a52e-9dcc8a008f50.json"
OUT = ROOT / "state" / "tool_fidelity.json"

TIMEOUT = 60

# The name under test. Capitalised on purpose -- that capital B is the entire experiment, because
# the observed failure was a route lowercasing it. Kept identical to Claude Code's real tool name so
# a pass here means the real client will work, not merely that some tool round-tripped.
TOOL_NAME = "Bash"

TOOLS = [{
    "name": TOOL_NAME,
    "description": "Run a shell command and return its stdout.",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The command to run"}},
        "required": ["command"],
    },
}]

# The prompt must NEVER contain the tool's name. First version of this script said "using the Bash
# tool", which handed the model the capital B to copy -- so a route that lowercases names from its
# own habit still scored tools_ok. The name has to come from the tools array and nowhere else, or
# the probe is only testing whether the model can echo the prompt back.
#
# Still phrased to leave no reasonable alternative to calling the tool, so `no_tool_use` means the
# route dropped the tools array rather than that the model merely preferred to chat.
PROMPT = ("Run the shell command `echo hi` and report its output. You have a tool available for "
          "running shell commands -- use it. Do not answer in prose.")

# --heavy sends the shape that actually broke, because the one-tool request above does NOT reproduce
# it: antigravity returns an exact `Bash` on the light probe and still failed every dispatch inside a
# real session. The differences worth testing are all size -- Claude Code ships the full tool set and
# a long system prompt. If a route silently drops or truncates the tools array once the request gets
# big, the model still knows from the system prompt that it ought to be calling tools, so it invents
# one from habit. An invented shell tool gets written `bash`; an invented file reader gets written
# `read`. Those are precisely the two names the harness rejected, which fits the evidence far better
# than the gateway rewriting a name it demonstrably round-trips correctly.
HEAVY_TOOL_NAMES = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "TodoWrite", "WebFetch",
                    "WebSearch", "Task", "NotebookEdit", "BashOutput", "KillShell", "ExitPlanMode"]

HEAVY_SYSTEM = ("You are an interactive CLI tool that helps users with software engineering tasks. "
                "Use the available tools to inspect and modify the codebase. Prefer the dedicated "
                "file and search tools over shell commands when one fits. Never guess at file "
                "contents -- read the file. " * 40)

WALL_TEXT = ("payment required", "insufficient credit", "insufficient_quota", "quota exceeded",
             "billing", "add a payment", "upgrade your plan", "captcha")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _tool_calls(body: dict) -> list[str]:
    """Every tool name this response tried to call, across both wire shapes.

    Anthropic /v1/messages puts them in content blocks of type tool_use. Some gateway members
    answer OpenAI-shaped even on this endpoint, so tool_calls[].function.name is checked too --
    that difference is itself a fidelity problem worth recording rather than crashing on.
    """
    names: list[str] = []
    content = body.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                names.append(str(block.get("name") or ""))
    try:
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        for call in (msg.get("tool_calls") or []):
            fn = (call or {}).get("function") or {}
            if fn.get("name"):
                names.append(str(fn["name"]))
    except (AttributeError, IndexError, TypeError):
        pass
    return [n for n in names if n]


def _text(body: dict) -> str:
    """Assistant prose, either wire shape -- only used to show what a no_tool_use route said."""
    content = body.get("content")
    if isinstance(content, list):
        joined = "".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
        if joined.strip():
            return joined.strip()
    try:
        choice = (body.get("choices") or [{}])[0]
        return str(((choice.get("message") or {}).get("content")) or "").strip()
    except (AttributeError, IndexError, TypeError):
        return ""


def _heavy_tools() -> list[dict]:
    """The full client tool set. Bash keeps its real schema so the verdict stays comparable to the
    light probe; the rest exist to make the tools array big, which is the variable under test."""
    tools = list(TOOLS)
    for name in HEAVY_TOOL_NAMES:
        if name == TOOL_NAME:
            continue
        tools.append({
            "name": name,
            "description": (f"The {name} tool. " * 12).strip(),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to operate on"},
                    "pattern": {"type": "string", "description": "Pattern to match"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": [],
            },
        })
    return tools


def probe(model_id: str, heavy: bool = False, timeout: int = TIMEOUT) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {"model": model_id, "mode": "heavy" if heavy else "light"}
    payload: dict[str, Any] = {
        "model": model_id, "max_tokens": 256,
        "tools": _heavy_tools() if heavy else TOOLS,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    if heavy:
        payload["system"] = HEAVY_SYSTEM
    row["toolsSent"] = len(payload["tools"])
    try:
        r = requests.post(f"{BASE}/v1/messages", json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:
        row.update(verdict="error", toolSafe=False, httpStatus=None,
                   errorType=type(e).__name__,
                   latencyMs=round((time.perf_counter() - started) * 1000))
        return row

    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
    row["httpStatus"] = r.status_code
    raw = r.text or ""
    try:
        body = r.json()
    except ValueError:
        body = {}

    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    detail = str(err.get("message") or body.get("detail") or body.get("message") or "")[:200]
    low = (detail + " " + raw[:300]).lower()
    if detail:
        row["detail"] = detail

    if r.status_code != 200:
        if r.status_code == 402 or any(w in low for w in WALL_TEXT):
            row["verdict"] = "wall"
        elif r.status_code == 429:
            row["verdict"] = "rate"
        elif r.status_code in (401, 403):
            row["verdict"] = "auth"
        elif r.status_code == 404:
            row["verdict"] = "not_routed"
        else:
            row["verdict"] = "error"
        row["toolSafe"] = False
        return row

    names = _tool_calls(body)
    row["toolNamesReturned"] = names
    if not names:
        said = _text(body)
        row.update(verdict=("no_tool_use" if said else "empty"), toolSafe=False,
                   sample=said[:80] or None,
                   stopReason=str(body.get("stop_reason") or "") or None)
        return row

    if TOOL_NAME in names:
        row.update(verdict="tools_ok", toolSafe=True)
    else:
        # The antigravity failure: a tool_use block came back, but under a name the client's
        # registry does not contain. Record exactly what it sent -- that string is the evidence.
        row.update(verdict="tools_mangled", toolSafe=False,
                   expected=TOOL_NAME, got=names[0],
                   note="tool_use returned under a name the client cannot dispatch")
    return row


def _models(a: argparse.Namespace) -> list[str]:
    if a.models:
        return [m.strip() for m in a.models.split(",") if m.strip()]
    cfg = pathlib.Path(a.config)
    if not cfg.exists():
        raise SystemExit(f"config not found: {cfg}")
    d = json.loads(cfg.read_text(encoding="utf-8"))
    return [str(m["name"]) for m in d.get("inferenceModels", []) if m.get("name")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--models", default="", help="comma-separated route ids to probe instead")
    ap.add_argument("--heavy", action="store_true",
                    help="send the full client tool set and a long system prompt (the shape that "
                         "actually broke); the light probe does not reproduce the failure")
    a = ap.parse_args()

    models = _models(a)
    mode = "heavy" if a.heavy else "light"
    log(f"tool-use fidelity [{mode}]: {len(models)} routes, tool name under test = {TOOL_NAME!r}")

    report: dict[str, Any] = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "endpoint": "/v1/messages",
        "mode": mode,
        "toolNameUnderTest": TOOL_NAME,
        "question": ("given a tool named exactly 'Bash', does the route call it back by exactly "
                     "that name? a route that lowercases it answers chat fine and breaks every "
                     "action an agentic client tries to take"),
        "timeoutSeconds": TIMEOUT,
        "results": [],
    }

    for m in models:
        row = probe(m, heavy=a.heavy)
        report["results"].append(row)
        mark = "OK  " if row.get("toolSafe") else "    "
        extra = ""
        if row["verdict"] == "tools_mangled":
            extra = f"  expected {row['expected']!r} got {row['got']!r}"
        elif row["verdict"] == "no_tool_use":
            extra = f"  said: {(row.get('sample') or '')[:40]!r}"
        elif row.get("detail"):
            extra = f"  {row['detail'][:60]}"
        log(f"  {mark}{m:38s} {row['verdict']:14s} {row.get('latencyMs')}ms{extra}")
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    safe = [r["model"] for r in report["results"] if r.get("toolSafe")]
    mangled = [r["model"] for r in report["results"] if r["verdict"] == "tools_mangled"]
    report["summary"] = {
        "toolSafe": safe,
        "toolMangled": mangled,
        "otherFailures": [r["model"] for r in report["results"]
                          if not r.get("toolSafe") and r["verdict"] != "tools_mangled"],
        "recommendedForAgenticClients": safe,
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    log("")
    log(f"tool-safe   ({len(safe)}): {', '.join(safe) or 'none'}")
    if mangled:
        log(f"MANGLED     ({len(mangled)}): {', '.join(mangled)}  <- do not use for Claude Code")
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
