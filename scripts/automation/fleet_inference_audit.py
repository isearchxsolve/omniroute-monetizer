#!/usr/bin/env python3
"""Run redacted, valid chat-completion probes for the OmniRoute model forest."""
from __future__ import annotations

import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import argparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:20128/v1"
AUDIT_PATH = PROJECT_ROOT / "state" / "fleet_provider_audit.json"
OUTPUT = PROJECT_ROOT / "state" / "fleet_inference_audit.json"

# These represent the ten catalog-level cascade coverage categories from the
# ledger. Each remains a concrete, standard chat-completion route.
CASCADE_ROUTES = {
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
UNSUITABLE = ("image", "video", "audio", "tts", "speech", "embedding", "rerank", "moderation", "vision")
PREFERRED = ("free", "flash", "mini", "nano", "small", "lite", "instant")


def candidates(models: list[dict[str, Any]], owner: str) -> list[str]:
    values = [str(m.get("id")) for m in models if str(m.get("owned_by", "")).lower() == owner.lower()]
    values = [v for v in values if not any(token in v.lower() for token in UNSUITABLE)]
    canonical = [v for v in values if v.lower().startswith(owner.lower() + "/")]
    values = canonical + [v for v in values if v not in canonical]
    return sorted(values, key=lambda v: (not any(token in v.lower() for token in PREFERRED), len(v)))[:3]


def probe(label: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "max_tokens": 60,
        "temperature": 0,
        "stream": False,
    }
    started = time.perf_counter()
    try:
        response = requests.post(f"{BASE}/chat/completions", json=payload, timeout=60)
        elapsed = round((time.perf_counter() - started) * 1000)
        success = response.status_code == 200
        # Do not persist an upstream response body: valid evidence is the HTTP
        # status and OpenAI-compatible choices shape, never text/token data.
        if success:
            try:
                success = isinstance(response.json().get("choices"), list)
            except ValueError:
                success = False
        return {"label": label, "model": model, "httpStatus": response.status_code, "latencyMs": elapsed, "valid": success}
    except requests.RequestException as exc:
        return {"label": label, "model": model, "httpStatus": None, "latencyMs": round((time.perf_counter() - started) * 1000), "valid": False, "error": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owners", nargs="*", help="Limit direct probes to these provider owners")
    parser.add_argument("--cascade-keys", nargs="*", help="Limit cascade probes to these ledger coverage keys")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Sanitized result JSON path")
    parser.add_argument(
        "--include-active-unhealthy",
        action="store_true",
        help="Also probe active owners whose native health check is currently false; useful for re-verification.",
    )
    args = parser.parse_args()
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    models_response = requests.get(f"{BASE}/models", timeout=120)
    models_response.raise_for_status()
    models = models_response.json().get("data", [])
    active_owners = sorted({
        c["provider"]
        for c in audit["connections"]
        if c["isActive"] and (c["test"]["valid"] or args.include_active_unhealthy)
    })
    if args.owners is not None:
        wanted = {owner.lower() for owner in args.owners}
        active_owners = [owner for owner in active_owners if owner.lower() in wanted]
    cascade_routes = CASCADE_ROUTES
    if args.cascade_keys is not None:
        wanted = {key.lower() for key in args.cascade_keys}
        cascade_routes = {key: model for key, model in CASCADE_ROUTES.items() if key.lower() in wanted}
    def probe_owner(owner: str) -> dict[str, Any]:
        choices = candidates(models, owner)
        if not choices:
            return {"label": f"direct:{owner}", "valid": False, "error": "no_catalog_model"}
        attempts = [probe(f"direct:{owner}", model) for model in choices]
        selected = dict(next((item for item in attempts if item["valid"]), attempts[-1]))
        selected["attempts"] = attempts
        return selected

    with ThreadPoolExecutor(max_workers=8) as pool:
        direct = list(pool.map(probe_owner, active_owners))
    with ThreadPoolExecutor(max_workers=5) as pool:
        cascade = list(pool.map(lambda pair: probe(f"cascade:{pair[0]}", pair[1]), cascade_routes.items()))
    results = direct + cascade
    summary = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "payload": "standard_chat_completion:max_tokens=60",
        "modelCatalogCount": len(models),
        "total": len(results),
        "valid": sum(1 for item in results if item.get("valid")),
        "failed": sum(1 for item in results if not item.get("valid")),
        "results": results,
    }
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"total={summary['total']} valid={summary['valid']} failed={summary['failed']} output={args.output}")
    for item in results:
        print(f"{item['label']} status={item.get('httpStatus')} valid={item.get('valid')} latency_ms={item.get('latencyMs')} model={item.get('model', '-')}")
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
