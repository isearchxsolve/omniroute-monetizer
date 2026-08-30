#!/usr/bin/env python3
"""Audit the real :8190 consumer surface without pretending inventory is capacity.

The consumer endpoint intentionally merges two *distinct* harnesses:

* OmniRoute (:20128): provider connections and their advertised model catalog.
* Session pool (:8190 local seats): browser-captured chat/video sessions.

An advertised model, an active connection, a replay capture, and a completed request
are four different facts.  This script preserves those distinctions.  Its optional
``--probe`` mode sends exactly one Law-3 computed chat request through each selected
healthy route; it never bulk-probes the catalog or retries a wall/rate-limit route.

Default selection is deliberately narrow: the public ``frontier`` Omni cascade plus
the unpinned ``session-pool/auto`` route.  Supply-specific checks can be requested
with ``--model`` (repeatable) after a provider/account has been selected as healthy.
Video is reported as inventory versus proven durable-job capacity only; submitting a
new video job is intentionally outside this audit because it can spend credits.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "state" / "merged_healthy_capacity_audit.json"
CONSUMER = "http://127.0.0.1:8190/v1"
OMNI = "http://127.0.0.1:20128"
COMPUTED_PROMPT = "Reply with only the number: 41 + 17"
EXPECTED = "58"


def get_json(url: str, timeout: int = 15) -> tuple[dict[str, Any], int | None, str | None]:
    try:
        r = requests.get(url, timeout=timeout)
        return (r.json() if r.ok else {}), r.status_code, None
    except (requests.RequestException, ValueError) as exc:
        return {}, None, f"{type(exc).__name__}: {exc}"[:240]


def assistant_text(body: dict[str, Any]) -> str:
    try:
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(str(p.get("text") or "") for p in content if isinstance(p, dict)).strip()
    except (AttributeError, IndexError):
        pass
    return ""


def probe(model: str, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {"model": model}
    try:
        response = requests.post(
            f"{CONSUMER}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": COMPUTED_PROMPT}],
                  "temperature": 0, "max_tokens": 20},
            timeout=timeout,
        )
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        row.update(healthy=False, verdict="transport_error", error=f"{type(exc).__name__}: {exc}"[:240])
    else:
        answer = assistant_text(body)
        error = body.get("error") if isinstance(body, dict) else {}
        row.update(
            healthy=response.status_code == 200 and answer == EXPECTED,
            verdict="ok" if response.status_code == 200 and answer == EXPECTED else "not_verified",
            httpStatus=response.status_code,
            answer=answer[:80],
            provider=body.get("provider"),
            session=body.get("session"),
            gatewaySource=body.get("x_gateway_source"),
            gatewayFallbackReason=body.get("x_gateway_fallback_reason"),
            error=(str(error.get("message") or "")[:240] if isinstance(error, dict) else ""),
        )
    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="send one computed request per selected route")
    parser.add_argument("--model", action="append", default=[], help="additional already-selected healthy route")
    parser.add_argument("--timeout", type=int, default=75)
    args = parser.parse_args()

    consumer, consumer_status, consumer_error = get_json(f"{CONSUMER}/models")
    omni, omni_status, omni_error = get_json(f"{OMNI}/v1/models")
    merged_models = consumer.get("data") or []
    omni_models = omni.get("data") or []
    metadata = consumer.get("x_gateway") if isinstance(consumer.get("x_gateway"), dict) else {}

    owners = Counter(str(m.get("owned_by") or "unknown") for m in omni_models if isinstance(m, dict))
    local = [m for m in merged_models if isinstance(m, dict) and m.get("owned_by") == "session_pool"]
    chat_seats = [m for m in local if not str(m.get("id") or "").startswith("video/") and m.get("id") != "session-pool/auto"]
    video_seats = [m for m in local if str(m.get("id") or "").startswith("video/") and m.get("id") != "video/auto"]

    video_inventory_path = ROOT / "state" / "video_route_inventory.json"
    video_inventory: dict[str, Any] = {}
    if video_inventory_path.exists():
        try:
            video_inventory = json.loads(video_inventory_path.read_text(encoding="utf-8"))
        except ValueError:
            video_inventory = {"readError": "invalid JSON"}

    report: dict[str, Any] = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "consumer": {"base": CONSUMER, "modelsHttpStatus": consumer_status, "error": consumer_error,
                     "mergedAdvertisedModelCount": len(merged_models), "gateway": metadata},
        "omniRouteHarness": {
            "base": OMNI, "modelsHttpStatus": omni_status, "error": omni_error,
            "advertisedModelCount": len(omni_models), "providerModelCounts": dict(sorted(owners.items())),
            "meaning": "advertised provider/model inventory; not a health or account-capacity claim",
        },
        "seatPoolHarness": {
            "advertisedLocalChatSeatRoutes": len(chat_seats),
            "advertisedLocalVideoSeatRoutes": len(video_seats),
            "chatRouteIds": sorted(str(m.get("id")) for m in chat_seats),
            "videoRouteIds": sorted(str(m.get("id")) for m in video_seats),
            "meaning": "currently dispatchable local routes; final health requires a fresh computed response or completed video job",
        },
        "video": {
            "omniAdvertisedVideoInventory": video_inventory.get("total_video_routes"),
            "seatPoolProvenModelCount": (video_inventory.get("provenModelCount") if video_inventory else None),
            "meaning": "video model names are not chat-completion proof. Count completed durable jobs separately.",
        },
        "probes": [],
    }
    if args.probe:
        selected = ["frontier", "session-pool/auto", *args.model]
        for model in dict.fromkeys(selected):
            report["probes"].append(probe(model, args.timeout))
    report["verifiedHealthyRouteCount"] = sum(1 for row in report["probes"] if row.get("healthy"))

    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"output={OUT}")
    print(f"merged_advertised={len(merged_models)} omni_inventory={len(omni_models)} "
          f"seat_chat={len(chat_seats)} seat_video={len(video_seats)} "
          f"verified={report['verifiedHealthyRouteCount']}")
    for row in report["probes"]:
        print(f"probe model={row['model']} verdict={row.get('verdict')} healthy={row.get('healthy')} "
              f"source={row.get('gatewaySource')} provider={row.get('provider')} latencyMs={row.get('latencyMs')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
