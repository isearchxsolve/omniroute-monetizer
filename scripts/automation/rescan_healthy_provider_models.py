#!/usr/bin/env python3
"""Exhaustively rescan healthy OmniRoute connections and confirm chat models."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

BASE = "http://localhost:20128"
OUTPUT = PROJECT_ROOT / "state" / "healthy_provider_models_rescan.json"


def response_has_content(response: requests.Response) -> bool:
    """Accept JSON or SSE responses, but require a non-empty assistant answer."""
    try:
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        delta = choice.get("delta") or {}
        return bool((message.get("content") or delta.get("content") or "").strip())
    except (ValueError, IndexError, AttributeError):
        for line in response.text.splitlines():
            if line.startswith("data:") and "[DONE]" not in line and '"content"' in line:
                return True
        return False


def probe(model_id: str, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{BASE}/v1/chat/completions",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                "stream": False,
                "temperature": 0,
                "max_tokens": 20,
            },
            timeout=timeout,
        )
        latency = round((time.perf_counter() - started) * 1000)
        return {
            "model": model_id,
            "valid": response.status_code == 200 and response_has_content(response),
            "httpStatus": response.status_code,
            "latencyMs": latency,
        }
    except requests.RequestException as exc:
        return {
            "model": model_id,
            "valid": False,
            "httpStatus": None,
            "latencyMs": round((time.perf_counter() - started) * 1000),
            "errorType": type(exc).__name__,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("ERROR management login failed")
        return 1

    connections = api.get_connections()
    healthy_connections: list[dict[str, Any]] = []
    for connection in connections:
        if not connection.get("isActive"):
            continue
        result = api.test_connection(str(connection["id"]))
        body = result.get("result") or {}
        if body.get("valid"):
            healthy_connections.append(connection)

    print(f"healthy_connections={len(healthy_connections)} total_connections={len(connections)}")
    work: list[tuple[str, str, str]] = []
    connection_models: dict[str, list[str]] = {}
    for connection in healthy_connections:
        provider = str(connection.get("provider") or "unknown")
        connection_id = str(connection["id"])
        models = sorted(set(api.connection_models(connection_id)))
        connection_models[connection_id] = models
        work.extend((connection_id, provider, model) for model in models)
        print(f"models provider={provider} connection={connection_id} count={len(models)}")

    # Deduplicate the request list while retaining every connection's ownership.
    unique_work = sorted(set(work), key=lambda item: (item[1], item[2], item[0]))
    print(f"models_to_probe={len(unique_work)} workers={args.workers}")
    confirmed_by_provider: dict[str, set[str]] = {}
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(probe, model, args.timeout): (connection_id, provider, model)
            for connection_id, provider, model in unique_work
        }
        for index, future in enumerate(as_completed(futures), start=1):
            connection_id, provider, model = futures[future]
            result = future.result()
            result.update({"provider": provider, "connectionId": connection_id})
            results.append(result)
            if result["valid"]:
                confirmed_by_provider.setdefault(provider, set()).add(model)
            if index % 25 == 0 or index == len(futures):
                print(f"completed={index}/{len(futures)} confirmed={sum(len(v) for v in confirmed_by_provider.values())}")

    provider_rows = []
    for connection in healthy_connections:
        provider = str(connection.get("provider") or "unknown")
        provider_rows.append({
            "provider": provider,
            "connectionId": str(connection["id"]),
            "name": connection.get("name"),
            "modelIds": sorted(confirmed_by_provider.get(provider, set())),
        })

    report = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": "valid management test plus per-connection model list plus real chat completion",
        "totalConnections": len(connections),
        "healthyConnectionCount": len(healthy_connections),
        "candidateModelRouteCount": len(unique_work),
        "confirmedModelRouteCount": sum(1 for result in results if result["valid"]),
        "healthyProviders": sorted({row["provider"] for row in provider_rows}),
        "providers": sorted(provider_rows, key=lambda row: (row["provider"], row["connectionId"])),
        "results": sorted(results, key=lambda result: (result["provider"], result["model"], result["connectionId"])),
    }
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())