#!/usr/bin/env python3
"""OmniRoute's provider-by-model graduation master.

This is the OmniRoute equivalent of ``fleet_graduation.py``.  It keeps the
harnesses distinct while making their final admission rule identical:

  OmniRoute catalog -> one serial lane per provider -> computed direct proof
  -> computed pinned proof through http://127.0.0.1:8190/v1
  -> exact provider/model admission ledger

The default action is a read-only plan.  ``--apply --e2e`` performs inference
requests.  ``--confirm-video-spend`` is additionally required when the native
video sweep is requested because native video verification consumes credits.

This file never changes OmniRoute's database, stops/restarts a service, or
fabricates health from an active connection/model catalog.  It uses the
published management API and the two published inference faces only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
RUN = STATE / "omniroute_graduation_run.json"
ADMISSIONS = STATE / "omniroute_verified_routes.json"
VIDEO_REPORT = STATE / "video_provider_probe.json"
OMNI = "http://127.0.0.1:20128"
CONSUMER = "http://127.0.0.1:8190/v1"
PROMPT = "Reply with only the number: 41 + 17"
EXPECTED = "58"
VIDEO_PROMPT = "A five second abstract blue-and-gold ocean wave, no text."
WALL_WORDS = ("payment", "billing", "quota", "credit", "captcha", "upgrade", "insufficient")

sys.path.insert(0, str(HERE))
from omniroute_api import OmniRouteAPI, extract_chat_content, get_password  # noqa: E402


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: pathlib.Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def no_proxy_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


class GlobalRequestGate:
    """Bound live load sent to the single OmniRoute process.

    Provider lanes preserve breadth, but OmniRoute is still one local gateway.  Without a
    second global bound, ten provider lanes can simultaneously occupy the gateway with slow
    upstream work.  The gate is deliberately process-local and does not change provider
    credentials or service state.
    """

    def __init__(self, max_inflight: int = 2, min_interval: float = 1.0) -> None:
        self._semaphore = threading.BoundedSemaphore(max(1, int(max_inflight)))
        self._interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._next_start = 0.0

    def __enter__(self) -> "GlobalRequestGate":
        self._semaphore.acquire()
        try:
            with self._lock:
                now = time.monotonic()
                delay = max(0.0, self._next_start - now)
                self._next_start = max(now, self._next_start) + self._interval
            if delay:
                time.sleep(delay)
            return self
        except BaseException:
            self._semaphore.release()
            raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._semaphore.release()


def assistant_text(body: Any, raw: str = "") -> str:
    text = extract_chat_content(body, raw)
    return str(text or "").strip()


def classify_failure(status: int | None, body: Any, raw: str = "") -> str:
    low = (str(body) + " " + raw[:600]).lower()
    if status in (401, 403):
        return "AUTH"
    if status == 402 or any(w in low for w in WALL_WORDS):
        return "WALL"
    if status == 429:
        return "RATE"
    if status == 404:
        return "NOT_ROUTED"
    if status == 200:
        return "EMPTY"
    return "ERROR"


def live_catalog(session: requests.Session) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    try:
        response = session.get(f"{OMNI}/v1/models", timeout=30)
        payload = response.json() if response.ok else {}
        rows = [r for r in payload.get("data", []) if isinstance(r, dict) and r.get("id")]
        meta = {"http": response.status_code, "count": len(rows),
                "latencyMs": round((time.perf_counter() - started) * 1000)}
        if not response.ok:
            # A protected catalog returning 401 is an authentication/configuration
            # failure, not an empty fleet.  Keeping it explicit prevents a master
            # graduation run from silently claiming there are zero routes.
            meta["error"] = f"HTTP_{response.status_code}"
        return rows, meta
    except Exception as exc:
        return [], {"http": None, "count": 0, "error": f"{type(exc).__name__}: {exc}"[:220]}


def authenticated_live_catalog() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the protected direct catalog using the normal local management session.

    OmniRoute 3.8.50 correctly requires its local management cookie for
    ``/v1/models``.  A bare request produces 401 and used to abort the master
    before any provider proof.  This helper is discovery-only: it never changes
    a provider, combo, key, database, or consumer setting.
    """
    api = OmniRouteAPI(base_url=OMNI, password=get_password())
    api.session.trust_env = False
    try:
        if not api.login():
            return [], {"http": None, "count": 0, "error": "MANAGEMENT_LOGIN_FAILED"}
        rows, meta = live_catalog(api.session)
        meta["authenticated"] = True
        return rows, meta
    except Exception as exc:
        return [], {"http": None, "count": 0,
                    "error": f"AUTHENTICATED_CATALOG_{type(exc).__name__}: {exc}"[:220]}


def provider_name(row: dict[str, Any]) -> str:
    # owned_by is the catalog's routing owner.  Keep it separate from any
    # provider string returned by a downstream response.
    return str(row.get("owned_by") or row.get("provider") or "unknown")


def is_non_chat(row: dict[str, Any]) -> bool:
    mid = str(row.get("id") or "").lower()
    return (mid.startswith("video/") or any(x in mid for x in
            ("/veo", "/wan", "/kling", "/luma", "text-to-video", "image-generation")))


def catalog_modality(row: dict[str, Any]) -> str:
    """Classify a catalog row without erasing models from the capacity ledger.

    OmniRoute providers routinely expose chat and video-capable models together.  The
    chat completion master must not send a text chat payload to a native video model,
    but it must also never make that model disappear merely because its provider is
    primarily a chat provider.  ``video_candidate`` therefore remains an inventory
    row until the native video contract proves (or rejects) it.
    """
    return "video_candidate" if is_non_chat(row) else "chat"


def plan_from_catalog(catalog: list[dict[str, Any]], max_models: int = 0) -> list[dict[str, Any]]:
    rows = []
    for item in catalog:
        model = str(item.get("id") or "")
        owner = provider_name(item)
        if not model or owner in {"combo", "session_pool", "unknown"} or is_non_chat(item):
            continue
        rows.append({"provider": owner, "model": model,
                     "modelFamily": model_family(model), "catalogOwnedBy": owner})
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["provider"]].append(row)
    # All models are the production default.  A cap is an explicit diagnostic
    # mode and is recorded so a partial run can never look like full capacity.
    for owner in grouped:
        grouped[owner] = sorted(grouped[owner], key=lambda r: r["model"])
        if max_models:
            grouped[owner] = grouped[owner][:max_models]
    return [row for owner in sorted(grouped) for row in grouped[owner]]


def capability_inventory(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep every concrete Omni provider/model row visible for final capacity truth.

    This is intentionally separate from ``plan_from_catalog``: the latter is a
    chat-completions execution plan, while this ledger is the provider-by-model
    inventory used to decide which native modality runner must be built or invoked.
    """
    rows: list[dict[str, Any]] = []
    for item in catalog:
        model = str(item.get("id") or "")
        owner = provider_name(item)
        if not model or owner in {"combo", "session_pool", "unknown"}:
            continue
        modality = catalog_modality(item)
        rows.append({"provider": owner, "model": model, "modelFamily": model_family(model),
                     "modality": modality, "catalogOwnedBy": owner,
                     "executionState": (
                         "CHAT_COMPLETIONS_CANDIDATE" if modality == "chat"
                         else "NATIVE_VIDEO_CONTRACT_REQUIRED"
                     )})
    return sorted(rows, key=lambda r: (r["provider"], r["model"]))


def model_family(model: str) -> str:
    low = model.lower()
    if any(x in low for x in ("code", "coder", "codex", "program")):
        return "coding"
    if any(x in low for x in ("reason", "think", "r1", "qwq", "o1", "o3", "o4")):
        return "reasoning"
    if any(x in low for x in ("vision", "vl", "omni")):
        return "multimodal"
    if any(x in low for x in ("embed", "rerank", "tts", "audio")):
        return "non-chat"
    return "chat"


def direct_probe(session: requests.Session, route: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    result = {**route, "directProof": "NOT_PROVEN", "http": None}
    try:
        response = session.post(f"{OMNI}/v1/chat/completions", json={
            "model": route["model"],
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0, "max_tokens": 32, "stream": False,
        }, timeout=timeout)
        raw = response.text or ""
        body = response.json() if response.status_code == 200 else {}
        answer = assistant_text(body, raw)
        result.update(http=response.status_code, answer=answer[:80],
                      directProof="DIRECT_LAW3_OK" if response.status_code == 200 and answer == EXPECTED
                      else classify_failure(response.status_code, body, raw))
    except Exception as exc:
        result.update(directProof="TRANSPORT", error=f"{type(exc).__name__}: {exc}"[:220])
    result["latencyMs"] = round((time.perf_counter() - started) * 1000)
    return result


def consumer_probe(session: requests.Session, row: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    result = {"provider": row["provider"], "model": row["model"],
              "modelFamily": row["modelFamily"], "consumerModel": row["model"],
              "consumerProof": "NOT_PROVEN"}
    try:
        response = session.post(f"{CONSUMER}/chat/completions", json={
            "model": row["model"],
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0, "max_tokens": 32, "stream": False,
        }, timeout=timeout)
        raw = response.text or ""
        body = response.json() if response.status_code == 200 else {}
        answer = assistant_text(body, raw)
        result.update(http=response.status_code, answer=answer[:80],
                      gatewaySource=body.get("x_gateway_source") if isinstance(body, dict) else None,
                      consumerProof="CONSUMER_LAW3_OK" if response.status_code == 200 and answer == EXPECTED
                      else classify_failure(response.status_code, body, raw))
    except Exception as exc:
        result.update(consumerProof="TRANSPORT", error=f"{type(exc).__name__}: {exc}"[:220])
    result["latencyMs"] = round((time.perf_counter() - started) * 1000)
    return result


def management_snapshot() -> dict[str, Any]:
    """Read provider connection metadata through OmniRoute's management API."""
    api = OmniRouteAPI(base_url=OMNI, password=get_password())
    api.session.trust_env = False
    try:
        if not api.login():
            return {"auth": "FAILED", "connections": []}
        connections = api.get_connections()
        active = [c for c in connections if c.get("isActive")]
        return {"auth": "OK", "total": len(connections), "active": len(active),
                "connections": [{"id": str(c.get("id") or ""),
                                 "provider": str(c.get("provider") or ""),
                                 "isActive": bool(c.get("isActive")),
                                 "authType": str(c.get("authType") or "")}
                                for c in connections]}
    except Exception as exc:
        return {"auth": "ERROR", "connections": [], "error": f"{type(exc).__name__}: {exc}"[:220]}


def build_plan(*, include_management: bool = True) -> dict[str, Any]:
    catalog, catalog_meta = authenticated_live_catalog()
    # Connection metadata is useful for a read-only plan, but it is not a
    # prerequisite for route graduation.  A wedged /api/providers endpoint
    # must not hold the production inference pass hostage after catalog
    # discovery has succeeded.
    management = management_snapshot() if include_management else {
        "auth": "SKIPPED_E2E_OPTIONAL_METADATA", "connections": []}
    routes = plan_from_catalog(catalog)
    capability_rows = capability_inventory(catalog)
    return {"schemaVersion": 1, "generatedAt": now(),
            "mode": "omniroute_all_catalog_plan_no_inference", "endpoint": OMNI,
            "consumerContract": CONSUMER, "catalog": catalog_meta,
            "management": {k: v for k, v in management.items() if k != "connections"},
            "providers": dict(Counter(r["provider"] for r in routes)),
            "routes": routes,
            "providerModelCapabilityInventory": capability_rows,
            "capabilityCounts": dict(Counter(r["modality"] for r in capability_rows)),
            "whatThisDoesNotProve": ["current provider health", "credentials", "quota",
                                      "consumer reachability", "video render success", "capacity"],
            "videoInterpretation": (
                "video_candidate rows are concrete provider/model inventory, not excluded chat-provider "
                "noise and not completed-video capacity. They require the native video contract runner."
            )}


def prior_route_results(payload: Any) -> list[dict[str, Any]]:
    """Read either durable run schema written by this master.

    During a long direct sweep the temporary form has ``results`` at top level.
    At completion ``main`` persists the same evidence under ``chat.direct``.  Both
    are durable states of one execution, so treating the latter as empty caused a
    later resume to repeat already-terminal provider/model requests.
    """
    if not isinstance(payload, dict):
        return []
    direct = payload.get("results")
    if not isinstance(direct, list):
        chat = payload.get("chat")
        direct = chat.get("direct") if isinstance(chat, dict) else []
    return [row for row in direct if isinstance(row, dict)] if isinstance(direct, list) else []


def run_chat_e2e(plan: dict[str, Any], timeout: float, consumer_timeout: float,
                 lanes: int = 2, max_inflight: int = 2,
                 min_interval: float = 1.0, resume: bool = True) -> dict[str, Any]:
    prior_payload = read_json(RUN, {}) if resume else {}
    prior_rows = prior_route_results(prior_payload)
    prior = {(str(r.get("provider")), str(r.get("model"))): r for r in prior_rows
             if isinstance(r, dict) and r.get("provider") and r.get("model")}
    results: list[dict[str, Any]] = list(prior.values())
    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in plan.get("routes", []):
        by_provider[str(row["provider"])].append(row)
    write_lock = threading.Lock()
    request_gate = GlobalRequestGate(max_inflight=max_inflight, min_interval=min_interval)

    def record(result: dict[str, Any]) -> None:
        with write_lock:
            results.append(result)
            # Persist after every route: a long fleet run is resumable evidence.
            atomic_json(RUN, {"schemaVersion": 1, "updatedAt": now(),
                              "phase": "direct_provider_model_probes", "results": results})

    def provider_lane(owner: str, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One request at a time for this provider; independent providers may overlap."""
        session = no_proxy_session()
        lane_results: list[dict[str, Any]] = []
        strikes = 0
        for index, route in enumerate(routes):
            old = prior.get((owner, str(route["model"])))
            if old and old.get("directProof") not in {"TRANSPORT", "ERROR"}:
                lane_results.append(old)
                continue
            with request_gate:
                result = direct_probe(session, route, timeout)
            if result["directProof"] == "RATE":
                strikes += 1
                time.sleep(min(30, strikes * 5))
                with request_gate:
                    result = direct_probe(session, route, timeout)
            elif result["directProof"] == "DIRECT_LAW3_OK":
                strikes = 0
            lane_results.append(result)
            record(result)
            print(f"[{owner}] {index + 1}/{len(routes)} {route['model']} -> "
                  f"{result['directProof']}", flush=True)
            if result["directProof"] == "WALL":
                # A provider wall stops only this provider lane.
                for rest in routes[index + 1:]:
                    skipped = {**rest, "directProof": "SKIPPED_PROVIDER_WALL"}
                    lane_results.append(skipped)
                    record(skipped)
                break
        print(f"[{owner}] lane complete: {sum(r.get('directProof') == 'DIRECT_LAW3_OK' for r in lane_results)} "
              f"direct proofs / {len(lane_results)} rows", flush=True)
        return lane_results

    # This is the breadth-not-depth rule: up to N providers can be active,
    # while a given provider has exactly one in-flight request.
    with ThreadPoolExecutor(max_workers=max(1, lanes)) as executor:
        futures = [executor.submit(provider_lane, owner, routes)
                   for owner, routes in sorted(by_provider.items())]
        for future in as_completed(futures):
            future.result()  # direct_probe is per-route isolated; surface only an unexpected bug

    direct_ok = [r for r in results if r.get("directProof") == "DIRECT_LAW3_OK"]
    consumer_session = no_proxy_session()
    consumer = [consumer_probe(consumer_session, r, consumer_timeout) for r in direct_ok]
    admitted = [r for r in consumer if r.get("consumerProof") == "CONSUMER_LAW3_OK"]
    admissions = {"schemaVersion": 1, "generatedAt": now(),
                  "consumerContract": CONSUMER,
                  "entries": [{"provider": r["provider"], "model": r["model"],
                               "modelFamily": r["modelFamily"], "modality": "chat",
                               "state": "ADMITTED", "directProof": "DIRECT_LAW3_OK",
                               "consumerProof": "CONSUMER_LAW3_OK", "verifiedAt": now()}
                              for r in admitted]}
    atomic_json(ADMISSIONS, admissions)
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in admitted:
        matrix[r["provider"]][r["modelFamily"]] += 1
    return {"phase": "chat_direct_then_8190_consumer", "direct": results,
            "consumer": consumer, "admitted": admissions["entries"],
            "providerModelFamilyCapacity": {p: dict(v) for p, v in sorted(matrix.items())},
            "counts": {"directLaw3": len(direct_ok), "consumerLaw3": len(admitted)}}


def run_video_e2e(confirm: bool, timeout: int, max_routes: int) -> dict[str, Any]:
    if not confirm:
        return {"phase": "native_video", "state": "NOT_RUN",
                "reason": "requires --confirm-video-spend"}
    command = [sys.executable, str(HERE / "video_provider_probe.py"), "--all",
               "--timeout", str(timeout)]
    if max_routes:
        command += ["--max", str(max_routes)]
    env = os.environ.copy()
    env["OMNI_VIDEO_CONFIRM_SPEND"] = "1"
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    report = read_json(VIDEO_REPORT, {})
    working = report.get("working", []) if isinstance(report, dict) else []
    return {"phase": "native_video", "commandExit": completed.returncode,
            "endpoint": f"{OMNI}/v1/videos/generations", "workingModels": working,
            "state": "DIRECT_VIDEO_MP4_PROOF_RECORDED" if working else "NO_VIDEO_MP4_PROOF"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true", help="write the live catalog/management plan only")
    ap.add_argument("--apply", action="store_true", help="required before inference or video work")
    ap.add_argument("--e2e", action="store_true", help="run Omni chat graduation and native video proof")
    ap.add_argument("--confirm-video-spend", action="store_true",
                    help="required for native video MP4 generation")
    ap.add_argument("--timeout", type=float, default=45, help="one chat route request timeout")
    ap.add_argument("--consumer-timeout", type=float, default=90, help="one final :8190 request timeout")
    ap.add_argument("--lanes", type=int, default=2,
                    help="provider lanes (default 2); each provider remains one-request-at-a-time")
    ap.add_argument("--max-inflight", type=int, default=2,
                    help="global concurrent requests into OmniRoute (default 2)")
    ap.add_argument("--min-interval", type=float, default=1.0,
                    help="minimum global spacing between OmniRoute request starts in seconds")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore an interrupted omniroute_graduation_run.json; default resumes terminal route evidence")
    ap.add_argument("--video-timeout", type=int, default=900, help="one native video request timeout")
    ap.add_argument("--max-models-per-provider", type=int, default=0,
                    help="diagnostic cap; 0 means every catalog model")
    ap.add_argument("--max-video-routes", type=int, default=0,
                    help="diagnostic video cap; 0 means every video registry route")
    args = ap.parse_args()
    if args.e2e and not args.apply:
        ap.error("--apply is required with --e2e")
    if args.e2e and not args.confirm_video_spend:
        ap.error("--e2e requires --confirm-video-spend because native video proof spends capacity")

    plan = build_plan(include_management=not args.e2e)
    if args.e2e and not plan.get("routes"):
        ap.error("OmniRoute catalog returned no chat routes; service/catalog is unavailable, no probes started")
    if args.max_models_per_provider:
        plan["routes"] = plan_from_catalog(
            authenticated_live_catalog()[0], args.max_models_per_provider)
        plan["mode"] = "omniroute_capped_diagnostic_plan"
    atomic_json(STATE / "omniroute_graduation_plan.json", plan)
    if not args.e2e:
        print(f"plan={STATE / 'omniroute_graduation_plan.json'} providers={len(plan['providers'])} routes={len(plan['routes'])}")
        return 0

    chat = run_chat_e2e(plan, args.timeout, args.consumer_timeout, args.lanes,
                        args.max_inflight, args.min_interval, resume=not args.fresh)
    atomic_json(RUN, {"schemaVersion": 1, "generatedAt": now(), "endpoint": OMNI,
                      "consumerContract": CONSUMER, "chat": chat})
    video = run_video_e2e(args.confirm_video_spend, args.video_timeout, args.max_video_routes)
    final = read_json(RUN, {})
    final["video"] = video
    final["completedAt"] = now()
    atomic_json(RUN, final)
    print(f"run={RUN} directLaw3={chat['counts']['directLaw3']} "
          f"consumerLaw3={chat['counts']['consumerLaw3']} video={video['state']}")
    return 0 if chat["counts"]["consumerLaw3"] or video.get("workingModels") else 1


if __name__ == "__main__":
    raise SystemExit(main())
