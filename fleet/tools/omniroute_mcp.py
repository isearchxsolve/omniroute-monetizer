#!/usr/bin/env python3
"""
OMNIROUTE MCP SERVER (Phase 4)
Exposes the OmniRoute Agent Internet (web.execute, web.result, capture_execute)
as native tools to any Model Context Protocol (MCP) host (Claude Desktop, Cursor, Antigravity, Kilo).
Conforms to MCP JSON-RPC 2.0 over stdio.
"""
import sys
import json
import base64
import urllib.request
from pathlib import Path

# Add local path for capture_replay
sys.path.insert(0, str(Path(__file__).parent))
try:
    from capture_replay import execute_capture
except ImportError:
    execute_capture = None

DOOR = "https://omniroute-relay.omniroute-fleet-kd.workers.dev"
TOKEN = "GOLD24"

TOOLS = [
    {
        "name": "web_execute",
        "description": "Execute live HTTP requests against the web via OmniRoute permanent door (edge ~100ms or Kaggle fleet body)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The destination URL to fetch (http/https)"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "HEAD", "PATCH"],
                    "default": "GET",
                    "description": "HTTP request method"
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP request headers dictionary"
                },
                "body": {
                    "type": "string",
                    "description": "Raw string or JSON payload to send for POST/PUT"
                },
                "mode": {
                    "type": "string",
                    "enum": ["edge", "fleet"],
                    "description": "Execution path: 'edge' (Worker fast path ~100ms) or 'fleet' (Kaggle cloud body)"
                },
                "timeout_s": {
                    "type": "integer",
                    "default": 15,
                    "description": "Execution timeout in seconds"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "web_result",
        "description": "Retrieve the result of an asynchronous fleet execution job by job_id",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job ID returned by web_execute in fleet mode (e.g. wx_...)"
                }
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "capture_execute",
        "description": "Execute a pre-registered site-flow wire recipe from the capture registry with dynamic parameters and sentinel validation",
        "inputSchema": {
            "type": "object",
            "properties": {
                "capture_id": {
                    "type": "string",
                    "description": "The registry ID of the capture (e.g. 'github.get_zen.v1', 'httpbin.post_payload.v1', 'linkedin.search_jobs.v1')"
                },
                "params": {
                    "type": "object",
                    "description": "Parameters to inject into the wire templates"
                }
            },
            "required": ["capture_id"]
        }
    }
]

def handle_web_execute(args: dict) -> dict:
    url = args.get("url")
    method = (args.get("method") or "GET").upper()
    headers = args.get("headers") or {}
    body = args.get("body")
    mode = args.get("mode")
    timeout_s = args.get("timeout_s", 15)

    spec = {
        "url": url,
        "method": method,
        "headers": headers,
        "timeout_s": timeout_s
    }
    if body:
        spec["body"] = body
    if mode:
        spec["mode"] = mode

    req = urllib.request.Request(
        f"{DOOR}/v1/tools/web.execute?token={TOKEN}",
        data=json.dumps(spec).encode("utf-8"),
        headers={"content-type": "application/json", "User-Agent": "omniroute-mcp-client"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("result", {}).get("content_b64"):
            b64 = data["result"]["content_b64"]
            try:
                data["result"]["content_text"] = base64.b64decode(b64).decode("utf-8", "replace")[:5000]
            except Exception:
                pass
        return data
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def handle_web_result(args: dict) -> dict:
    jid = args.get("job_id")
    req = urllib.request.Request(
        f"{DOOR}/v1/tools/web.result?token={TOKEN}&job_id={jid}",
        headers={"User-Agent": "omniroute-mcp-client"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("content_b64"):
            try:
                data["content_text"] = base64.b64decode(data["content_b64"]).decode("utf-8", "replace")[:5000]
            except Exception:
                pass
        return data
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def handle_capture_execute(args: dict) -> dict:
    cid = args.get("capture_id")
    params = args.get("params") or {}
    if not execute_capture:
        return {"status": "failed", "error": "capture_replay module not available"}
    try:
        return execute_capture(cid, params=params)
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def process_message(msg: dict):
    m_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": m_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "omniroute-agent-internet",
                    "version": "1.0.0"
                }
            }
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": m_id,
            "result": {
                "tools": TOOLS
            }
        }

    if method == "tools/call":
        t_name = params.get("name")
        t_args = params.get("arguments") or {}
        if t_name == "web_execute":
            res = handle_web_execute(t_args)
        elif t_name == "web_result":
            res = handle_web_result(t_args)
        elif t_name == "capture_execute":
            res = handle_capture_execute(t_args)
        else:
            return {
                "jsonrpc": "2.0",
                "id": m_id,
                "error": {"code": -32601, "message": f"Tool '{t_name}' not found"}
            }
        return {
            "jsonrpc": "2.0",
            "id": m_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(res, indent=2)
                    }
                ]
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": m_id,
        "error": {"code": -32601, "message": f"Method '{method}' not implemented"}
    }

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = process_message(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
