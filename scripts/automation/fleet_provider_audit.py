#!/usr/bin/env python3
"""Redacted OmniRoute fleet audit and targeted recovery helper.

This deliberately uses the supported management REST API through the shared
client.  It never writes the database directly and never writes credentials,
cookie values, API keys, or passwords to output files.  The only persisted
artifact is a sanitized audit with connection metadata and endpoint outcomes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

OUTPUT = PROJECT_ROOT / "state" / "fleet_provider_audit.json"


def safe_text(value: Any, limit: int = 300) -> str:
    return redact(str(value)).replace("\n", " ")[:limit]


def sanitize_connection(conn: dict[str, Any]) -> dict[str, Any]:
    """Keep only non-secret connection fields useful for recovery."""
    return {
        "id": conn.get("id"),
        "provider": conn.get("provider"),
        "name": conn.get("name"),
        "authType": conn.get("authType"),
        "isActive": bool(conn.get("isActive")),
        "testStatus": conn.get("testStatus"),
        "hasCredential": bool(conn.get("apiKey")),
        "modelCount": len(conn.get("models") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reactivate-inactive", action="store_true")
    args = parser.parse_args()

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("ERROR management login failed")
        return 1

    connections = api.get_connections()
    results: dict[str, Any] = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "totalConnections": len(connections),
        "reactivateInactive": args.reactivate_inactive,
        "connections": [],
    }
    for conn in connections:
        entry = sanitize_connection(conn)
        cid = entry["id"]
        test = api.test_connection(cid)
        test_result = test.get("result") or {}
        entry["test"] = {
            "httpStatus": test.get("http_status"),
            "valid": bool(test_result.get("valid")),
            "latencyMs": test_result.get("latencyMs"),
            "diagnosis": safe_text(test_result.get("diagnosis") or test_result.get("error") or test_result.get("message") or ""),
        }
        # A disabled configured connection is only re-enabled after OmniRoute's
        # upstream test reports valid.  OAuth credentials live in provider
        # metadata rather than apiKey, so the valid test is the safe evidence
        # of an existing usable credential. The actual inference check remains
        # separate.
        if (
            args.reactivate_inactive
            and not entry["isActive"]
            and entry["test"]["valid"]
        ):
            update = api.update_connection(cid, {"isActive": True})
            entry["reactivation"] = {"httpStatus": update.get("http_status")}
            entry["isActive"] = update.get("http_status") in (200, 201)
            retest = api.test_connection(cid)
            body = retest.get("result") or {}
            entry["postReactivateTest"] = {
                "httpStatus": retest.get("http_status"),
                "valid": bool(body.get("valid")),
                "latencyMs": body.get("latencyMs"),
                "diagnosis": safe_text(body.get("diagnosis") or body.get("error") or body.get("message") or ""),
            }
        results["connections"].append(entry)

    OUTPUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    valid = sum(1 for c in results["connections"] if c["test"]["valid"])
    inactive = sum(1 for c in results["connections"] if not c["isActive"])
    print(f"total={len(connections)} valid_tests={valid} inactive_now={inactive} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
