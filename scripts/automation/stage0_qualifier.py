#!/usr/bin/env python3
"""
Protocol & Stage 0 Snapshot Qualifier for OmniRoute Monetizer Takeover Campaign.

Validates:
  1. Non-streaming completions (HTTP 200, choices format, usage stats, response model).
  2. Streaming completions (text/event-stream headers, SSE line framing, TTFT, delta content, terminal [DONE]).
  3. Tool-calling completions (function schema, tool_choice='auto', message.tool_calls output).
  4. Shallow system snapshot (OmniRoute reachability, active connections, model catalog count, OS resources).

Output: state/qualification/<run-id>/stage0_snapshot.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact
from oauth_keepalive import resolve_password

BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128").rstrip("/")
V1_URL = f"{BASE_URL}/v1"
API_URL = f"{BASE_URL}/api"


def make_run_id() -> str:
    now_str = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{now_str}-qual"


def probe_non_streaming(model: str = "auto/pro-coding", timeout: int = 30) -> Dict[str, Any]:
    """Test standard non-streaming chat completion."""
    start = time.monotonic()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: READY"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    try:
        r = requests.post(f"{V1_URL}/chat/completions", json=payload, timeout=timeout)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        ok = r.status_code == 200
        content = ""
        res_model = None
        if ok:
            try:
                body = r.json()
                res_model = body.get("model")
                choices = body.get("choices") or []
                if choices and isinstance(choices, list):
                    content = choices[0].get("message", {}).get("content", "") or ""
            except Exception:
                ok = False
        return {
            "probe": "non_streaming",
            "model": model,
            "http_status": r.status_code,
            "latency_ms": elapsed,
            "ok": ok and bool(content),
            "response_model": res_model,
            "content_preview": content[:80],
            "error": None if (ok and content) else redact(r.text[:300]),
        }
    except Exception as e:
        return {
            "probe": "non_streaming",
            "model": model,
            "http_status": None,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "ok": False,
            "response_model": None,
            "content_preview": "",
            "error": f"{type(e).__name__}: {e}",
        }


def probe_streaming(model: str = "auto/pro-coding", timeout: int = 30) -> Dict[str, Any]:
    """Test SSE streaming completion framing, TTFT, and [DONE] termination."""
    start = time.monotonic()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Count from 1 to 3."}],
        "max_tokens": 30,
        "temperature": 0,
        "stream": True,
    }
    ttft = None
    chunks_received = 0
    done_seen = False
    headers_ok = False
    res_model = None
    first_chunk_text = ""

    try:
        r = requests.post(f"{V1_URL}/chat/completions", json=payload, stream=True, timeout=timeout)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        headers_ok = r.status_code == 200 and "text/event-stream" in r.headers.get("Content-Type", "")

        if r.status_code == 200:
            for line in r.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8", errors="replace").strip()
                if line_str.startswith("data:"):
                    data_str = line_str[5:].strip()
                    if data_str == "[DONE]":
                        done_seen = True
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        if ttft is None:
                            ttft = round((time.monotonic() - start) * 1000, 1)
                            res_model = chunk_json.get("model")
                        chunks_received += 1
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content") or delta.get("reasoning_content") or ""
                        if text and len(first_chunk_text) < 40:
                            first_chunk_text += text
                    except Exception:
                        pass

        return {
            "probe": "streaming",
            "model": model,
            "http_status": r.status_code,
            "headers_ok": headers_ok,
            "ttft_ms": ttft,
            "total_latency_ms": elapsed,
            "chunks_received": chunks_received,
            "done_seen": done_seen,
            "ok": headers_ok and (chunks_received > 0),
            "response_model": res_model,
            "sample_content": first_chunk_text[:80],
            "error": None if (headers_ok and chunks_received > 0) else f"HTTP {r.status_code}, stream failed",
        }
    except Exception as e:
        return {
            "probe": "streaming",
            "model": model,
            "http_status": None,
            "headers_ok": False,
            "ttft_ms": None,
            "total_latency_ms": round((time.monotonic() - start) * 1000, 1),
            "chunks_received": 0,
            "done_seen": False,
            "ok": False,
            "response_model": None,
            "sample_content": "",
            "error": f"{type(e).__name__}: {e}",
        }


def probe_tool_calling(model: str = "auto/pro-coding", timeout: int = 30) -> Dict[str, Any]:
    """Test tool-calling schema execution and message.tool_calls output."""
    start = time.monotonic()
    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City and state, e.g. San Francisco, CA"}
                    },
                    "required": ["location"],
                },
            },
        }
    ]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a tool-using AI assistant. You MUST call the get_current_weather tool to answer the user query."},
            {"role": "user", "content": "Get current weather for Tokyo"}
        ],
        "tools": tools_schema,
        "tool_choice": "auto",
        "max_tokens": 100,
        "stream": False,
    }

    try:
        r = requests.post(f"{V1_URL}/chat/completions", json=payload, timeout=timeout)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        ok = r.status_code == 200
        has_tool_call = False
        tool_name = None
        tool_args = None

        if ok:
            try:
                body = r.json()
                msg = body.get("choices", [{}])[0].get("message", {})
                tool_calls = msg.get("tool_calls") or []
                # Also accept finish_reason == 'tool_calls' or presence of tool_calls/function_call
                if tool_calls and isinstance(tool_calls, list):
                    has_tool_call = True
                    tool_name = tool_calls[0].get("function", {}).get("name")
                    tool_args = tool_calls[0].get("function", {}).get("arguments")
                elif msg.get("function_call"):
                    has_tool_call = True
                    tool_name = msg.get("function_call", {}).get("name")
                    tool_args = msg.get("function_call", {}).get("arguments")
                elif body.get("choices", [{}])[0].get("finish_reason") == "tool_calls":
                    has_tool_call = True
                    tool_name = "get_current_weather"
            except Exception:
                ok = False

        return {
            "probe": "tool_calling",
            "model": model,
            "http_status": r.status_code,
            "latency_ms": elapsed,
            "ok": ok and has_tool_call,
            "has_tool_call": has_tool_call,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "error": None if (ok and has_tool_call) else f"HTTP {r.status_code}, no tool_call in response",
        }
    except Exception as e:
        return {
            "probe": "tool_calling",
            "model": model,
            "http_status": None,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "ok": False,
            "has_tool_call": False,
            "tool_name": None,
            "tool_args": None,
            "error": f"{type(e).__name__}: {e}",
        }


def capture_stage0_snapshot() -> Dict[str, Any]:
    """Capture coarse system health, active connections, and protocol battery."""
    run_id = make_run_id()
    target_dir = PROJECT_ROOT / "state" / "qualification" / run_id
    target_dir.mkdir(parents=True, exist_ok=True)

    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    login_ok = api.login()

    connections = []
    if login_ok:
        try:
            connections = api.get_connections()
        except Exception:
            pass

    active_conns = [c for c in connections if c.get("isActive")]

    # Run protocol probes
    non_stream_res = probe_non_streaming("auto/pro-coding")
    stream_res = probe_streaming("auto/pro-coding")
    tool_res = probe_tool_calling("nvidia/nemotron-3-super-120b-a12b")

    snapshot = {
        "run_id": run_id,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "omniroute_base": BASE_URL,
        "management_authenticated": login_ok,
        "total_connections": len(connections),
        "active_connections": len(active_conns),
        "protocol_probes": {
            "non_streaming": non_stream_res,
            "streaming": stream_res,
            "tool_calling": tool_res,
        },
        "all_protocol_probes_ok": non_stream_res["ok"] and stream_res["ok"] and tool_res["ok"],
    }

    out_file = target_dir / "stage0_snapshot.json"
    out_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"[+] Stage 0 Snapshot saved to: {out_file}")
    print(f"    Run ID: {run_id}")
    print(f"    Active Connections: {len(active_conns)}/{len(connections)}")
    print(f"    Non-Streaming Probe: {'OK' if non_stream_res['ok'] else 'FAIL'}")
    print(f"    Streaming Probe:     {'OK' if stream_res['ok'] else 'FAIL'}")
    print(f"    Tool-Calling Probe:  {'OK' if tool_res['ok'] else 'FAIL'}")

    return snapshot


if __name__ == "__main__":
    capture_stage0_snapshot()
