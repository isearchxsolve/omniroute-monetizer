#!/usr/bin/env python3
"""Bounded runtime checks for OmniRoute streaming and tool-call response contracts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

import requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from omniroute_api import extract_chat_content, get_api_key, redact  # noqa: E402

DEFAULT_OUTPUT = ROOT / "state" / "omniroute_contract_probe.json"


def sse_contract(raw: str) -> dict[str, bool]:
    return {"hasDataFrame": any(line.startswith("data:") for line in raw.splitlines()),
            "hasDone": any(line.strip() == "data: [DONE]" for line in raw.splitlines()),
            "hasContent": bool(extract_chat_content({}, raw))}


def tool_contract(body: Any) -> dict[str, bool]:
    if not isinstance(body, dict):
        return {"hasChoices": False, "hasToolCall": False, "hasContent": False}
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return {"hasChoices": False, "hasToolCall": False, "hasContent": False}
    message = choices[0].get("message") or {}
    return {"hasChoices": True, "hasToolCall": bool(isinstance(message, dict) and message.get("tool_calls")),
            "hasContent": bool(isinstance(message, dict) and message.get("content"))}


def post(base: str, payload: dict[str, Any], timeout: float, stream: bool = False) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    key = get_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return requests.post(f"{base}/v1/chat/completions", headers=headers, json=payload, timeout=timeout, stream=stream)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:20128")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    report: dict[str, Any] = {"generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "base": base,
                               "bounded": True, "stream": {}, "tools": {}}
    try:
        with post(base, {"model": "frontier", "messages": [{"role": "user", "content": "Reply with OK."}],
                         "max_tokens": 16, "temperature": 0, "stream": True}, args.timeout, stream=True) as response:
            raw = "".join(chunk.decode("utf-8", "replace") for chunk in response.iter_content(chunk_size=4096) if chunk)[:131072]
            report["stream"] = {"httpStatus": response.status_code, **sse_contract(raw)}
    except Exception as exc:
        report["stream"] = {"error": type(exc).__name__}
    tool_payload = {
        "model": "auto/pro-coding",
        "messages": [{"role": "user", "content": "Call the echo tool with text set to OK."}],
        "tools": [{"type": "function", "function": {"name": "echo", "description": "Return provided text.",
                   "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}],
        "tool_choice": {"type": "function", "function": {"name": "echo"}}, "max_tokens": 64, "temperature": 0,
        "stream": False,
    }
    try:
        response = post(base, tool_payload, args.timeout)
        try:
            body = response.json()
        except Exception:
            body = None
        report["tools"] = {"httpStatus": response.status_code, **tool_contract(body),
                           "nonJson": body is None, "error": None if response.status_code == 200 else redact(response.text)[:200]}
    except Exception as exc:
        report["tools"] = {"error": type(exc).__name__}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stream": report["stream"], "tools": report["tools"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
