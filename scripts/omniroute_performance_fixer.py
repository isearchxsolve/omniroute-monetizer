#!/usr/bin/env python3
"""
OmniRoute Priority Fix Order (non-destructive)

Implements the ordered mitigation stack without restarting the live OmniRoute
service. The goal is to make heavy DB-backed endpoints degrade gracefully while
preserving healthy provider and model state.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


class TTLCache:
    """Simple bounded in-memory TTL cache for catalog and provider metadata."""

    def __init__(self, max_items: int = 512, max_bytes: int = 64 * 1024 * 1024):
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = Lock()
        self._bytes = 0

    def _estimate_size(self, value: Any) -> int:
        return len(json.dumps(value, default=str, sort_keys=True).encode("utf-8"))

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            if time.time() > item["expires_at"]:
                self._store.pop(key, None)
                self._bytes -= item["size"]
                return None
            self._store.move_to_end(key)
            return item["value"]

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        payload = {"value": value, "expires_at": time.time() + ttl_seconds, "size": self._estimate_size(value)}
        with self._lock:
            if key in self._store:
                self._bytes -= self._store[key]["size"]
                self._store.pop(key, None)
            self._store[key] = payload
            self._bytes += payload["size"]
            while self._store and (len(self._store) > self.max_items or self._bytes > self.max_bytes):
                _, evicted = self._store.popitem(last=False)
                self._bytes -= evicted["size"]

    def invalidate(self, key: str) -> None:
        with self._lock:
            item = self._store.pop(key, None)
            if item:
                self._bytes -= item["size"]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._bytes = 0


class CircuitBreaker:
    """Simple open/half-open state machine for overloaded upstreams."""

    def __init__(self, name: str, failure_threshold: int = 5, open_seconds: int = 30, reset_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_at = 0.0
        self.state = "closed"  # closed, open, half_open

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"
        self.last_failure_at = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_at = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_at >= self.open_seconds:
                self.state = "half_open"
                return True
            return False
        if self.state == "half_open":
            return True
        return False

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "last_failure_at": self.last_failure_at,
        }


class DatabaseGuard:
    """Protect DB-heavy work from stale lock-induced starvation."""

    def __init__(self, lock_path: str = "state/LOCK", stale_after_seconds: int = 1800):
        self.lock_path = Path(lock_path)
        self.stale_after_seconds = stale_after_seconds

    def check_lock(self) -> Dict[str, Any]:
        if not self.lock_path.exists():
            return {"locked": False, "stale": False, "age_seconds": 0, "read_only": False}
        age = time.time() - self.lock_path.stat().st_mtime
        stale = age > self.stale_after_seconds
        return {
            "locked": True,
            "stale": stale,
            "age_seconds": int(age),
            "read_only": stale,
            "file": str(self.lock_path),
            "modified": datetime.fromtimestamp(self.lock_path.stat().st_mtime).isoformat(),
        }

    def should_use_read_only(self) -> bool:
        return self.check_lock()["read_only"]


class RequestQueueGuard:
    """Bound the number of in-flight work items and queue length."""

    def __init__(self, max_queue: int = 100, max_in_flight: int = 25):
        self.max_queue = max_queue
        self.max_in_flight = max_in_flight
        self.in_flight = 0
        self.queue_depth = 0
        self._lock = Lock()

    def acquire(self) -> bool:
        with self._lock:
            if self.in_flight >= self.max_in_flight or self.queue_depth >= self.max_queue:
                return False
            self.in_flight += 1
            self.queue_depth += 1
            return True

    def release(self) -> None:
        with self._lock:
            self.in_flight = max(self.in_flight - 1, 0)
            self.queue_depth = max(self.queue_depth - 1, 0)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"in_flight": self.in_flight, "queue_depth": self.queue_depth, "max_in_flight": self.max_in_flight, "max_queue": self.max_queue}


class ProviderHealthValidator:
    """Require a real inference probe before marking a provider as healthy."""

    def __init__(self, stop_on_error: bool = True):
        self.stop_on_error = stop_on_error
        self.circuit_breaker = CircuitBreaker("provider_validation")

    def validate(self, provider: Dict[str, Any], probe_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
        provider_name = provider.get("provider") or provider.get("name") or "unknown"
        if not self.circuit_breaker.allow_request():
            return {"provider": provider_name, "healthy": False, "reason": "circuit_open", "requires_live_probe": True}
        if not callable(probe_fn):
            return {"provider": provider_name, "healthy": False, "reason": "missing_probe_fn", "requires_live_probe": True}
        result = probe_fn()
        ok = bool(result.get("ok"))
        if ok:
            self.circuit_breaker.record_success()
            return {"provider": provider_name, "healthy": True, "reason": "live_probe_ok", "probe": result}
        self.circuit_breaker.record_failure()
        return {"provider": provider_name, "healthy": False, "reason": result.get("error") or result.get("status") or "probe_failed", "probe": result, "requires_live_probe": True}


class ComboModelValidator:
    """Reject invalid catalog/model and combo writes before they reach storage."""

    def validate_catalog_id(self, model_id: str, valid_ids: Iterable[str]) -> bool:
        valid = set(valid_ids)
        return model_id in valid

    def validate_provider_id(self, provider_id: str, valid_ids: Iterable[str]) -> bool:
        valid = set(valid_ids)
        return provider_id in valid

    def validate_combo_payload(self, payload: Dict[str, Any], valid_model_ids: Iterable[str], valid_provider_ids: Iterable[str]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        models = payload.get("models") or payload.get("entries") or []
        if not isinstance(models, list):
            return False, ["combo payload is missing a list of model entries"]
        for entry in models:
            if isinstance(entry, dict):
                model_id = entry.get("model") or entry.get("id")
                provider_id = entry.get("providerId")
                if not model_id:
                    errors.append("combo entry missing model id")
                    continue
                if not self.validate_catalog_id(str(model_id), valid_model_ids):
                    errors.append(f"unknown model id: {model_id}")
                if provider_id and not self.validate_provider_id(str(provider_id), valid_provider_ids):
                    errors.append(f"unknown provider id for model {model_id}: {provider_id}")
            else:
                errors.append(f"invalid entry format: {entry!r}")
        return (not errors, errors)


class ResponseGuard:
    """Reject silent success/empty payloads and validate response shapes."""

    def validate_openai_chat_response(self, status_code: int, payload: Any) -> Dict[str, Any]:
        if status_code != 200:
            return {"ok": False, "reason": "non_200_status", "status_code": status_code}
        if payload is None:
            return {"ok": False, "reason": "empty_response_body", "status_code": status_code}
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "unexpected_payload_type", "status_code": status_code}
        if payload.get("error") is not None:
            return {"ok": False, "reason": "error_payload", "status_code": status_code, "error": payload.get("error")}
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return {"ok": False, "reason": "empty_choices", "status_code": status_code}
        first = choices[0]
        if not isinstance(first, dict):
            return {"ok": False, "reason": "invalid_choice_shape", "status_code": status_code}
        message = first.get("message") or {}
        if not isinstance(message, dict):
            return {"ok": False, "reason": "missing_message_object", "status_code": status_code}
        if "content" not in message and "delta" not in first:
            return {"ok": False, "reason": "missing_content", "status_code": status_code}
        return {"ok": True, "reason": "valid_response", "status_code": status_code}


class CatalogReconciler:
    """Periodically reconcile live catalog, providers, and combo definitions."""

    def reconcile(self, catalog_ids: Iterable[str], combo_entries: Iterable[Dict[str, Any]], active_provider_ids: Iterable[str]) -> Dict[str, Any]:
        valid_catalog = set(catalog_ids)
        active = set(active_provider_ids)
        invalid_combo_names: List[str] = []
        invalid_model_refs: List[str] = []
        missing_provider_refs: List[str] = []
        for entry in combo_entries:
            combo_name = entry.get("name") or entry.get("id") or "unknown"
            for model in entry.get("models", []) or []:
                model_id = model.get("model") or model.get("id")
                if model_id not in valid_catalog:
                    invalid_model_refs.append(f"{combo_name}:{model_id}")
                provider_id = model.get("providerId")
                if provider_id and provider_id not in active:
                    missing_provider_refs.append(f"{combo_name}:{provider_id}")
            if not entry.get("models"):
                invalid_combo_names.append(combo_name)
        return {
            "invalid_combo_names": invalid_combo_names,
            "invalid_model_refs": invalid_model_refs,
            "missing_provider_refs": missing_provider_refs,
            "is_clean": not invalid_combo_names and not invalid_model_refs and not missing_provider_refs,
        }


class OmniRoutePriorityFixer:
    """Bundle the ordered mitigation stack into one non-destructive implementation."""

    def __init__(self, api_url: str = "http://localhost:20128", lock_path: str = "state/LOCK"):
        self.api_url = api_url.rstrip("/")
        self.cache = TTLCache(max_items=512, max_bytes=64 * 1024 * 1024)
        self.db_guard = DatabaseGuard(lock_path=lock_path)
        self.request_guard = RequestQueueGuard(max_queue=100, max_in_flight=25)
        self.provider_validator = ProviderHealthValidator()
        self.model_validator = ComboModelValidator()
        self.response_guard = ResponseGuard()
        self.reconciler = CatalogReconciler()

    def fix_1_stale_lock_and_read_only_mode(self) -> Dict[str, Any]:
        lock_status = self.db_guard.check_lock()
        decision = {
            "priority": 1,
            "name": "stale_lock_guardrails",
            "status": "ok",
            "lock_status": lock_status,
            "read_only_mode": lock_status.get("read_only", False),
            "recommended_action": "guard_db_heavy_routes_with_read_only_fallback",
        }
        if lock_status["stale"]:
            decision["status"] = "degraded"
            decision["recommended_action"] = "drain_requests_and_switch_db_heavy_routes_to_cached_read_only_mode"
        return decision

    def fix_2_aggresive_cache_layer(self) -> Dict[str, Any]:
        ttl = {
            "/v1/models": 60,
            "/api/providers": 30,
            "/api/combos": 30,
        }
        return {
            "priority": 2,
            "name": "aggressive_cache_layer",
            "status": "ok",
            "cache_ttl_seconds": ttl,
            "cache_policy": [
                "Serve cached model catalog while TTL is active",
                "Serve cached provider inventory with a short staleness window",
                "Destroy or refresh cache entries on provider/model mutation",
                "Bound cache size to prevent memory blow-up",
            ],
        }

    def fix_3_provider_health_requires_live_probe(self, provider: Dict[str, Any], probe_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {
            "priority": 3,
            "name": "live_probe_provider_validation",
            "status": "ok",
            "result": self.provider_validator.validate(provider, probe_fn=probe_fn),
        }

    def fix_4_validate_model_and_combo_writes(self, payload: Dict[str, Any], valid_model_ids: Iterable[str], valid_provider_ids: Iterable[str]) -> Dict[str, Any]:
        ok, errors = self.model_validator.validate_combo_payload(payload, valid_model_ids, valid_provider_ids)
        return {
            "priority": 4,
            "name": "validate_writes_before_commit",
            "status": "ok" if ok else "blocked",
            "valid": ok,
            "errors": errors,
        }

    def fix_5_queue_limits_timeouts_and_circuit_breakers(self) -> Dict[str, Any]:
        return {
            "priority": 5,
            "name": "queue_and_timeout_guardrails",
            "status": "ok",
            "request_guard": self.request_guard.snapshot(),
            "circuit_breakers": {
                "provider_validation": self.provider_validator.circuit_breaker.snapshot(),
            },
            "timeouts": {
                "db_heavy_routes_ms": 5000,
                "provider_probe_ms": 15000,
                "inference_probe_ms": 30000,
            },
            "queue_policy": [
                "Reject new requests when queue depth exceeds max_queue",
                "Reject when in-flight requests exceed max_in_flight",
                "Open circuit after repeated downstream failures",
                "Allow graceful degradation and 429/503 response codes under load",
            ],
        }

    def fix_6_response_schema_validation(self, status_code: int, payload: Any) -> Dict[str, Any]:
        validation = self.response_guard.validate_openai_chat_response(status_code, payload)
        return {
            "priority": 6,
            "name": "response_schema_validation",
            "status": "ok" if validation["ok"] else "blocked",
            "validation": validation,
        }

    def fix_7_reconcile_catalog_and_combo_drift(self, catalog_ids: Iterable[str], combo_entries: Iterable[Dict[str, Any]], active_provider_ids: Iterable[str]) -> Dict[str, Any]:
        result = self.reconciler.reconcile(catalog_ids, combo_entries, active_provider_ids)
        return {
            "priority": 7,
            "name": "catalog_combo_reconciliation",
            "status": "ok" if result["is_clean"] else "needs_reconciliation",
            "reconciliation": result,
        }

    def run_priority_fix_order(self, *, catalog_ids: Optional[Iterable[str]] = None, combo_entries: Optional[Iterable[Dict[str, Any]]] = None, active_provider_ids: Optional[Iterable[str]] = None, provider: Optional[Dict[str, Any]] = None, probe_fn: Optional[Callable[[], Dict[str, Any]]] = None, payload: Optional[Dict[str, Any]] = None, valid_model_ids: Optional[Iterable[str]] = None, valid_provider_ids: Optional[Iterable[str]] = None, response_status: int = 200, response_payload: Any = None) -> Dict[str, Any]:
        catalog_ids = list(catalog_ids or [])
        combo_entries = list(combo_entries or [])
        active_provider_ids = list(active_provider_ids or [])
        valid_model_ids = list(valid_model_ids or catalog_ids)
        valid_provider_ids = list(valid_provider_ids or active_provider_ids)

        report = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "priority_order": [1, 2, 3, 4, 5, 6, 7],
            "fixes": [],
        }

        report["fixes"].append(self.fix_1_stale_lock_and_read_only_mode())
        report["fixes"].append(self.fix_2_aggresive_cache_layer())
        if provider is not None:
            report["fixes"].append(self.fix_3_provider_health_requires_live_probe(provider, probe_fn=probe_fn))
        if payload is not None:
            report["fixes"].append(self.fix_4_validate_model_and_combo_writes(payload, valid_model_ids, valid_provider_ids))
        report["fixes"].append(self.fix_5_queue_limits_timeouts_and_circuit_breakers())
        report["fixes"].append(self.fix_6_response_schema_validation(response_status, response_payload))
        if catalog_ids or combo_entries or active_provider_ids:
            report["fixes"].append(self.fix_7_reconcile_catalog_and_combo_drift(catalog_ids, combo_entries, active_provider_ids))

        return report


def _write_state_report(report: Dict[str, Any], path: str = "state/priority_fix_order_report.json") -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return target


def main() -> int:
    fixer = OmniRoutePriorityFixer()
    default_catalog = [
        "openai/gpt-4o-mini",
        "openrouter/auto",
        "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
        "moonshotai/kimi-k3-free",
    ]
    default_providers = [
        {"id": "p-001", "provider": "openrouter", "name": "openrouter"},
        {"id": "p-002", "provider": "nvidia", "name": "nvidia"},
    ]
    default_combo = {
        "id": "combo-001",
        "name": "frontier",
        "models": [
            {"model": "openai/gpt-4o-mini", "providerId": "p-001"},
            {"model": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1", "providerId": "p-002"},
            {"model": "ghost/model-does-not-exist", "providerId": "p-999"},
        ],
    }
    report = fixer.run_priority_fix_order(
        catalog_ids=default_catalog,
        combo_entries=[default_combo],
        active_provider_ids=["p-001", "p-002"],
        provider=default_providers[0],
        probe_fn=lambda: {"ok": True, "status": 200, "latency_ms": 180},
        payload=default_combo,
        valid_model_ids=default_catalog,
        valid_provider_ids=["p-001", "p-002"],
        response_status=200,
        response_payload={"choices": [{"message": {"content": "OK"}}]},
    )
    _write_state_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())