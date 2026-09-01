#!/usr/bin/env python3
"""Return a redacted authenticated OmniRoute catalog probe as one JSON line.

The management-protected ``/v1/models`` endpoint cannot be validated with a
bare curl request.  This tiny executable is intentionally separate from the
PowerShell cutover orchestrator so Windows command-line quote handling cannot
change the Python program being executed during a service migration.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from password_vault import retrieve_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:20128")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    session = requests.Session()
    session.trust_env = False
    started = time.perf_counter()
    result: dict[str, object]
    try:
        login = session.post(
            args.base.rstrip("/") + "/api/auth/login",
            json={"password": retrieve_password().strip()},
            timeout=120,
        )
        if login.status_code != 200:
            raise RuntimeError(f"management login HTTP {login.status_code}")
        response = session.get(args.base.rstrip("/") + "/v1/models", timeout=args.timeout)
        payload = response.json() if response.ok else {}
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        result = {
            "ok": response.status_code == 200 and isinstance(rows, list),
            "status": response.status_code,
            "count": len(rows),
            "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:  # Exact exception class/message, never a secret or response body.
        result = {
            "ok": False,
            "status": None,
            "count": 0,
            "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {str(exc)[:220]}",
        }
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
