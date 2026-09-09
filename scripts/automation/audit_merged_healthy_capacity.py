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
The final report deliberately preserves the units that must not be added together:

* ``verifiedOmniModels``: concrete provider/model pairs with direct and consumer
  Law-3 admission.  This is the only model-count capacity figure.
* ``verifiedSeatSessions``: exact browser-session files admitted after a replay
  proof.  A host/auto seat does not enumerate the models behind its web UI, so it
  is never silently counted as one model.
* ``verifiedVideoSeats``: exact video session files with submit-poll-result
  admission.  A video model name is not a completed-job proof.

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
TENANT_MAP = ROOT / "state" / "secrets" / "tenant_map.json"
OMNI_ADMISSIONS = ROOT / "state" / "omniroute_verified_routes.json"
SEAT_REGISTRY = ROOT / "state" / "pure_python_replay_registry.json"
SEAT_VIDEO_RUN = ROOT / "state" / "fleet_e2e_video_graduation_run.json"
COMPUTED_PROMPT = "Reply with only the number: 41 + 17"
EXPECTED = "58"


def consumer_auth_headers() -> dict[str, str]:
    """Return one tenant bearer without ever printing or persisting it.

    The merged consumer intentionally requires a tenant key when ``tenant_map.json`` exists. An
    unauthenticated catalog response is not an empty catalog; it is an auth failure. This helper
    keeps the read-only audit aligned with the real consumer contract while retaining an empty
    header for fresh installs that have no tenant map yet.
    """
    try:
        mapping = json.loads(TENANT_MAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(mapping, dict):
        return {}
    key = next((k for k in mapping if isinstance(k, str) and k.startswith("sk-")), None)
    return {"Authorization": f"Bearer {key}"} if key else {}


def get_json(url: str, timeout: int = 15, headers: dict[str, str] | None = None) -> tuple[dict[str, Any], int | None, str | None]:
    session = requests.Session()
    session.trust_env = False  # 127.0.0.1 must not be sent through the system proxy.
    try:
        r = session.get(url, headers=headers or {}, timeout=timeout)
        return (r.json() if r.ok else {}), r.status_code, None
    except (requests.RequestException, ValueError) as exc:
        return {}, None, f"{type(exc).__name__}: {exc}"[:240]


def get_omni_catalog() -> tuple[dict[str, Any], int | None, str | None, str]:
    """Read OmniRoute's auth-gated catalog through its management session.

    ``/v1/models`` is intentionally protected on the live instance. Sending the consumer tenant
    bearer (or no bearer) to OmniRoute is the wrong credential and yields HTTP 401. A management
    login followed by the same session cookie is read-only and mirrors how the dashboard reads the
    catalog. The final field records the auth mode without persisting the cookie or password.
    """
    try:
        import sys
        sys.path.insert(0, str(ROOT / "scripts" / "automation"))
        from omniroute_api import OmniRouteAPI, get_password

        password = get_password()
        if password:
            api = OmniRouteAPI(base_url=OMNI, password=password)
            if api.login():
                response = api.session.get(f"{OMNI}/v1/models", timeout=120)
                try:
                    body = response.json() if response.ok else {}
                except ValueError:
                    body = {}
                if response.ok and isinstance(body, dict):
                    return body, response.status_code, None, "management_cookie"
                return {}, response.status_code, "authenticated catalog request failed", "management_cookie"
    except (OSError, ValueError, requests.RequestException, RuntimeError) as exc:
        return {}, None, f"{type(exc).__name__}: {exc}"[:240], "unavailable"

    body, status, error = get_json(f"{OMNI}/v1/models")
    return body, status, error, "unauthenticated_fallback"


def load_json(path: Path) -> dict[str, Any]:
    """Load a non-secret evidence artifact; malformed or absent evidence is empty."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def verified_omni_entries(raw: dict[str, Any]) -> list[dict[str, str]]:
    """Return only concrete provider/model admissions, never catalog inventory."""
    rows: list[dict[str, str]] = []
    for entry in raw.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if not (
            entry.get("state") == "ADMITTED"
            and entry.get("directProof") == "DIRECT_LAW3_OK"
            and entry.get("consumerProof") == "CONSUMER_LAW3_OK"
        ):
            continue
        provider, model = str(entry.get("provider") or ""), str(entry.get("model") or "")
        if provider and model:
            rows.append({"provider": provider, "model": model,
                         "modality": str(entry.get("modality") or "chat")})
    return rows


def verified_seat_entries(raw: dict[str, Any]) -> list[dict[str, str]]:
    """Return exact admitted seat files.  A seat is a session unit, not a model count."""
    rows: list[dict[str, str]] = []
    for entry in raw.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("state") != "ADMITTED":
            continue
        host, session_file = str(entry.get("host") or ""), str(entry.get("sessionFile") or "")
        modality = str(entry.get("modality") or "chat")
        if host and session_file:
            rows.append({"provider": host, "sessionFile": session_file, "modality": modality,
                         "adapter": str(entry.get("adapter") or "")})
    return rows


def model_capacity_rows(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Group verified Omni admissions as provider × concrete models × modality."""
    grouped: dict[tuple[str, str], set[str]] = {}
    for entry in entries:
        grouped.setdefault((entry["provider"], entry["modality"]), set()).add(entry["model"])
    return [
        {"harness": "omniroute", "provider": provider, "modality": modality,
         "capacityUnit": "verified_provider_model", "verifiedModelCount": len(models),
         "models": sorted(models)}
        for (provider, modality), models in sorted(grouped.items())
    ]


def seat_capacity_rows(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Group verified seat artifacts without inventing hidden UI model identities."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for entry in entries:
        grouped.setdefault((entry["provider"], entry["modality"]), []).append(entry)
    rows: list[dict[str, Any]] = []
    for (provider, modality), seats in sorted(grouped.items()):
        rows.append({
            "harness": "seat_pool", "provider": provider, "modality": modality,
            "capacityUnit": "verified_exact_session",
            "verifiedSessionCount": len({seat["sessionFile"] for seat in seats}),
            "sessionFiles": sorted({seat["sessionFile"] for seat in seats}),
            "models": [],
            "modelIdentity": "UNENUMERATED_BY_SESSION_ARTIFACT_NOT_COUNTED_AS_ONE_MODEL",
        })
    return rows


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
    session = requests.Session()
    session.trust_env = False  # local contract is explicitly 127.0.0.1, never localhost/proxy.
    try:
        response = session.post(
            f"{CONSUMER}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": COMPUTED_PROMPT}],
                  "temperature": 0, "max_tokens": 20},
            headers=consumer_auth_headers(),
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

    consumer, consumer_status, consumer_error = get_json(
        f"{CONSUMER}/models", headers=consumer_auth_headers())
    omni, omni_status, omni_error, omni_auth_mode = get_omni_catalog()
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

    omni_admitted = verified_omni_entries(load_json(OMNI_ADMISSIONS))
    seat_admitted = verified_seat_entries(load_json(SEAT_REGISTRY))
    seat_video_run = load_json(SEAT_VIDEO_RUN)
    completed_video_jobs = [row for row in seat_video_run.get("consumerProofs") or []
                            if isinstance(row, dict) and row.get("state") == "CONSUMER_E2E_PROVEN"
                            and row.get("resultUrlObserved") is True]
    capacity_rows = [*model_capacity_rows(omni_admitted), *seat_capacity_rows(seat_admitted)]
    seat_chat = [entry for entry in seat_admitted if entry["modality"] == "chat"]
    seat_video = [entry for entry in seat_admitted if entry["modality"] == "video"]

    report: dict[str, Any] = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "consumer": {"base": CONSUMER, "modelsHttpStatus": consumer_status, "error": consumer_error,
                     "mergedAdvertisedModelCount": len(merged_models), "gateway": metadata},
        "omniRouteHarness": {
            "base": OMNI, "modelsHttpStatus": omni_status, "error": omni_error,
            "authMode": omni_auth_mode,
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
        "verifiedHealthyCapacity": {
            "unitsMustNotBeAdded": [
                "verified_provider_model", "verified_exact_session", "verified_completed_video_job"
            ],
            "verifiedOmniModels": len({(row["provider"], row["model"], row["modality"])
                                         for row in omni_admitted}),
            "verifiedSeatSessions": len({row["sessionFile"] for row in seat_admitted}),
            "verifiedSeatChatSessions": len({row["sessionFile"] for row in seat_chat}),
            "verifiedSeatVideoSessions": len({row["sessionFile"] for row in seat_video}),
            "verifiedConsumerVideoJobs": len(completed_video_jobs),
            "rows": capacity_rows,
            "meaning": (
                "Omni counts concrete admitted provider/model pairs. Seat-pool counts exact admitted "
                "sessions. A seat host that exposes an auto route does not disclose its internal model "
                "set in the session artifact and is therefore never misreported as one model."
            ),
        },
        "video": {
            "omniAdvertisedVideoInventory": video_inventory.get("total_video_routes"),
            "seatPoolProvenModelCount": None,
            "seatPoolVerifiedCompletedJobs": len(completed_video_jobs),
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
          f"verified_probes={report['verifiedHealthyRouteCount']} "
          f"verified_omni_models={report['verifiedHealthyCapacity']['verifiedOmniModels']} "
          f"verified_seat_sessions={report['verifiedHealthyCapacity']['verifiedSeatSessions']} "
          f"verified_video_jobs={report['verifiedHealthyCapacity']['verifiedConsumerVideoJobs']}")
    for row in report["probes"]:
        print(f"probe model={row['model']} verdict={row.get('verdict')} healthy={row.get('healthy')} "
              f"source={row.get('gatewaySource')} provider={row.get('provider')} latencyMs={row.get('latencyMs')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
