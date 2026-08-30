#!/usr/bin/env python3
"""Read-only OmniRoute capability matrix.

This probe deliberately performs GET requests only.  It records HTTP status,
elapsed time, response shape, and a small set of non-sensitive top-level keys;
it never sends prompts, writes configuration, reads credentials, or restarts a
service.  Run it after the owner-managed runtime is responsive:

    python scripts/automation/omniroute_capability_matrix.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE = "http://127.0.0.1:20128"
DEFAULT_OUTPUT = pathlib.Path("state/omniroute_capability_matrix.json")
PATHS = {
    "health": "/health",
    "models": "/v1/models",
    "combos": "/api/combos",
    "compression_status": "/api/compression/status",
    "relay_proxies": "/api/relay-proxies",
}


def _shape(body: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {"bytes": len(body)}
    try:
        value = json.loads(body.decode("utf-8", "replace"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result["json"] = False
        return result
    result["json"] = True
    if isinstance(value, dict):
        result["type"] = "object"
        result["keys"] = sorted(str(k) for k in value.keys())[:40]
        for key in ("data", "models", "combos", "providers", "status", "engine"):
            if key in value:
                item = value[key]
                result[f"{key}Type"] = type(item).__name__
                if isinstance(item, (list, dict)):
                    result[f"{key}Count"] = len(item)
    elif isinstance(value, list):
        result.update({"type": "array", "count": len(value)})
    else:
        result["type"] = type(value).__name__
    return result


def probe(url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_000)
            result: dict[str, Any] = {"status": response.status, "ok": 200 <= response.status < 300}
            result["contentType"] = response.headers.get("Content-Type", "")
            result["shape"] = _shape(body)
    except urllib.error.HTTPError as exc:
        result = {"status": exc.code, "ok": False, "error": "http_error"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result = {"status": None, "ok": False, "error": type(exc).__name__}
    result["elapsedMs"] = round((time.monotonic() - started) * 1000, 1)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=DEFAULT_BASE, help="read-only OmniRoute base URL")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base": base,
        "readOnly": True,
        "paths": {name: probe(base + path, args.timeout) for name, path in PATHS.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "readOnly": True,
        "allHealthy": all(item.get("ok") for item in report["paths"].values()),
        "paths": {name: {"status": item.get("status"), "error": item.get("error")} for name, item in report["paths"].items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
