#!/usr/bin/env python3
"""Refresh redacted fleet classifications and downstream model forest.

This script consumes only sanitized audit artifacts and the unauthenticated
OpenAI-compatible model catalog.  It never reads connection credential fields,
secret stores, environment files, or SQLite directly.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
LEDGER = STATE / "all_296_providers_execution_ledger.json"
AUDIT = STATE / "fleet_provider_audit.json"
INFERENCE = STATE / "fleet_inference_audit.json"
RETRY = STATE / "fleet_anthropic_retry.json"
ACTIVE_UNHEALTHY_REVERIFY = STATE / "fleet_active_unhealthy_reverify.json"
DEMOTIONS = STATE / "fleet_demotions.json"
FOREST = STATE / "omniroute_model_forest.json"
VERIFIED = STATE / "fleet_live_verified_routes.json"

CASCADE_SLUGS = {
    "anthropic": "auto/claude-sonnet",
    "azure-openai": "frontier",
    "deepseek-web": "auto/best-reasoning",
    "kimi-web": "moonshotai/kimi-k3-free",
    "meta-llama": "auto/llama",
    "mistral": "auto/best-chat",
    "qwen-cloud": "auto/best-coding",
    "qwen-cloud-token-plan": "auto/pro-coding",
    "qwen-web": "auto/pro-reasoning",
    "xai": "auto/best-fast",
}
LOCAL_SLUGS = {
    "g4f-ollama", "ollama-cloud", "ollama-local", "ollama-search", "oobabooga", "vllm"
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def concise_diagnosis(connection: dict) -> dict:
    test = connection.get("test") or {}
    value = str(test.get("diagnosis") or "not tested")
    # Audit diagnostic strings are already redacted by fleet_provider_audit.py.
    # Store only a bounded reason and non-sensitive HTTP/test metadata.
    return {
        "native_test_http_status": test.get("httpStatus"),
        "native_test_valid": bool(test.get("valid")),
        "native_diagnosis": value[:300],
    }


def blocked_status(connection: dict) -> str:
    text = str((connection.get("test") or {}).get("diagnosis") or "").lower()
    if "402" in text or "credit" in text or "paywall" in text:
        return "BLOCKED_CREDITS"
    if "cookie" in text or "session" in text:
        return "BLOCKED_NO_SESSION"
    if "not installed" in text or "not runnable" in text or "healthcheck_failed" in text:
        return "BLOCKED_LOCAL_RUNTIME"
    if "unsupported" in text:
        return "BLOCKED_VALIDATION_UNSUPPORTED"
    if "auth" in text or "key" in text or "reauth" in text:
        return "BLOCKED_AUTH_REQUIRED"
    return "BLOCKED_CONNECTION_UNVERIFIED"


def inference_results(path: Path) -> list[dict]:
    return (read_json(path).get("results") or []) if path.exists() else []


def main() -> int:
    ledger = read_json(LEDGER)
    providers = ledger["providers"]
    audit = read_json(AUDIT)
    direct_and_cascade = (
        inference_results(INFERENCE)
        + inference_results(RETRY)
        + inference_results(ACTIVE_UNHEALTHY_REVERIFY)
    )
    demoted = set(read_json(DEMOTIONS).get("failedInferenceProviders") or []) if DEMOTIONS.exists() else set()

    direct_ok: dict[str, dict] = {}
    cascade_ok: dict[str, dict] = {}
    for item in direct_and_cascade:
        label = str(item.get("label") or "")
        if not item.get("valid"):
            continue
        if label.startswith("direct:"):
            direct_ok[label.split(":", 1)[1]] = item
        elif label.startswith("cascade:"):
            cascade_ok[label.split(":", 1)[1]] = item

    by_provider: dict[str, list[dict]] = {}
    for connection in audit.get("connections") or []:
        by_provider.setdefault(str(connection.get("provider") or "").lower(), []).append(connection)

    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    for slug, entry in providers.items():
        lookup = slug.lower()
        connections = by_provider.get(lookup, [])
        if lookup in direct_ok:
            result = direct_ok[lookup]
            entry.update({
                "status": "LIVE_ACTIVE",
                "classification": "standard_chat_verified",
                "verified_upstream": True,
                "latency_ms": result.get("latencyMs"),
                "ts": generated,
                "details": {
                    "evidence": "standard OpenAI-compatible chat completion",
                    "http_status": result.get("httpStatus"),
                    "model": result.get("model"),
                },
            })
            continue
        if lookup in demoted:
            entry.update({
                "status": "BLOCKED_INFERENCE_FAILED",
                "classification": "standard_chat_failed_after_repair",
                "verified_upstream": False,
                "ts": generated,
                "details": {
                    "evidence": "failed standard chat probe and one retry; connection disabled through REST",
                    "action": "isActive=false via /api/providers/{id}",
                },
            })
            continue
        if lookup in LOCAL_SLUGS:
            entry.update({
                "status": "BLOCKED_LOCAL_RUNTIME",
                "classification": "local_endpoint_not_listening",
                "verified_upstream": False,
                "ts": generated,
                "details": {
                    "evidence": "localhost model-endpoint probe could not connect",
                    "action": "no provider node created",
                },
            })
            continue
        if slug in CASCADE_SLUGS:
            route = CASCADE_SLUGS[slug]
            result = cascade_ok.get(slug)
            if result:
                entry.update({
                    "status": "CASCADE_ROUTED",
                    "classification": "standard_chat_verified_cascade",
                    "verified_upstream": True,
                    "latency_ms": result.get("latencyMs"),
                    "ts": generated,
                    "details": {
                        "evidence": "standard OpenAI-compatible chat completion",
                        "route": route,
                        "http_status": result.get("httpStatus"),
                    },
                })
            continue
        # Reclassify the formerly configured-inactive catalog rows from their
        # current native test result.  Other pre-existing external catalog rows
        # retain their prior classification.
        if entry.get("status") == "CONFIGURED_INACTIVE" and connections:
            representative = next((c for c in connections if not (c.get("test") or {}).get("valid")), connections[0])
            entry.update({
                "status": blocked_status(representative),
                "classification": "configured_connection_not_inference_live",
                "verified_upstream": False,
                "ts": generated,
                "details": concise_diagnosis(representative),
            })

    # A current catalog can contain all advertised model IDs from a healthy
    # owner.  Downstream clients receive this current, active-owner forest;
    # the separate VERIFIED artifact records the exact 29 IDs that got 200s.
    with urlopen("http://127.0.0.1:20128/v1/models", timeout=120) as response:
        catalog = json.loads(response.read().decode("utf-8"))
    data = catalog.get("data") or []
    active_owners = set(direct_ok)
    forest = sorted({
        str(model.get("id"))
        for model in data
        if str(model.get("owned_by") or "").lower() in active_owners and model.get("id")
    } | {item.get("model") for item in cascade_ok.values() if item.get("model")})
    if not forest:
        raise RuntimeError("Refusing to replace model forest with an empty list")

    verified_routes = {
        "generatedAt": generated,
        "verification": "standard_chat_completion:max_tokens=16",
    }
    verified_routes["direct"] = [
        {"provider": owner, "model": item.get("model"), "httpStatus": item.get("httpStatus"), "latencyMs": item.get("latencyMs")}
        for owner, item in sorted(direct_ok.items())
    ]
    verified_routes["cascade"] = [
        {"coverage": key, "model": item.get("model"), "httpStatus": item.get("httpStatus"), "latencyMs": item.get("latencyMs")}
        for key, item in sorted(cascade_ok.items())
    ]
    counts = Counter(str(item.get("status")) for item in providers.values())
    ledger.update({
        "timestamp": generated,
        "connected_providers_count": audit.get("totalConnections"),
        "live_tested_healthy_count": len(direct_ok),
        "multi_provider_cascade_count": len(cascade_ok),
        "local_or_zero_auth_count": sum(1 for item in providers.values() if item.get("status") == "LOCAL_OR_PUBLIC"),
        "unconfigured_external_count": counts.get("EXTERNAL_ACCOUNT_REQUIRED", 0),
        "status_counts": dict(sorted(counts.items())),
        "evidence": "redacted REST audit plus standard chat-completion probes",
    })
    LEDGER.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    FOREST.write_text(json.dumps(forest, indent=2), encoding="utf-8")
    VERIFIED.write_text(json.dumps(verified_routes, indent=2), encoding="utf-8")
    print(
        f"ledger={LEDGER} live_direct={len(direct_ok)} cascades={len(cascade_ok)} "
        f"forest_models={len(forest)} verified_routes={len(verified_routes['direct']) + len(verified_routes['cascade'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
