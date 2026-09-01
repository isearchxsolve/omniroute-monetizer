#!/usr/bin/env python3
"""The production E2E acceptance master for the OmniRoute plane.

This is deliberately broader than a `GET /v1/models` check.  It certifies the
complete Omni path, without operating the separate seat-pool graduation harness:

  Omni service + connection inventory
    -> concrete provider x model capability ledger
    -> computed direct proof and Omni routing contracts
    -> authenticated merge at http://127.0.0.1:8190/v1
    -> authenticated OiiOii and Emergent customer execution surfaces
    -> durable, healthy-only release report

Default mode is read-only preflight.  `--apply --e2e` enables bounded
provider/model execution.  Consumer jobs and any native/video work are separate,
explicit spend gates; this command never fabricates their proof when the required
live credentials, application process, or consent are absent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import statistics
import sys
import time
from typing import Any

import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
OUT = STATE / "omniroute_e2e_acceptance.json"
OMNI = "http://127.0.0.1:20128"
GATEWAY = "http://127.0.0.1:8190/v1"
TENANT_MAP = STATE / "secrets" / "tenant_map.json"
OIOI_CONTRACT = pathlib.Path(r"D:\god_ai\oioi\oioi\backend\docs\CONSUMER_EXECUTION_CONTRACT.md")
EMERGENT_CONTRACT = pathlib.Path(r"D:\god_ai\emergentsh-standalone-clean\docs\CONSUMER_EXECUTION_CONTRACT.md")

sys.path.insert(0, str(HERE))
import omniroute_graduation as graduation  # noqa: E402
from omniroute_api import extract_chat_content, get_api_key  # noqa: E402


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False  # `localhost` is proxy-intercepted on this rig.
    return s


def error_name(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:240]


def plain_response(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = {}
    return {"http": response.status_code, "json": body if isinstance(body, dict) else {},
            "contentType": response.headers.get("Content-Type", "")[:120]}


def service_stability(base: str, samples: int, timeout: float) -> dict[str, Any]:
    """Read-only repeated catalog checks; a listening port alone is not stable serving."""
    rows: list[dict[str, Any]] = []
    for _ in range(max(1, samples)):
        started = time.perf_counter()
        try:
            response = session().get(f"{base.rstrip('/')}/v1/models", timeout=timeout)
            body = response.json() if response.ok else {}
            data = body.get("data") if isinstance(body, dict) else None
            rows.append({"http": response.status_code, "models": len(data) if isinstance(data, list) else 0,
                         "latencyMs": round((time.perf_counter() - started) * 1000)})
        except (requests.RequestException, ValueError) as exc:
            rows.append({"http": None, "models": 0, "error": error_name(exc),
                         "latencyMs": round((time.perf_counter() - started) * 1000)})
    passed = [row for row in rows if row.get("http") == 200 and row.get("models", 0) > 0]
    latencies = [int(row["latencyMs"]) for row in passed]
    return {"base": base, "samples": rows, "successfulSamples": len(passed),
            "state": "STABLE_CATALOG" if len(passed) == len(rows) else "UNSTABLE_OR_UNAVAILABLE",
            "medianLatencyMs": round(statistics.median(latencies)) if latencies else None}


def consumer_auth_gate(timeout: float) -> dict[str, Any]:
    """Verify gateway auth is genuinely enabled without reading tenant secrets."""
    gate_enabled = TENANT_MAP.is_file()
    result: dict[str, Any] = {"tenantMapPresent": gate_enabled, "gateway": GATEWAY}
    try:
        anonymous = session().get(f"{GATEWAY}/models", timeout=timeout)
        result["anonymousHttp"] = anonymous.status_code
    except requests.RequestException as exc:
        result.update(state="GATEWAY_UNAVAILABLE", error=error_name(exc))
        return result
    if not gate_enabled:
        result.update(state="AUTH_GATE_OPEN_BLOCKER",
                      reason="state/secrets/tenant_map.json is absent; shim intentionally permits open local mode")
        return result
    if result["anonymousHttp"] != 401:
        result.update(state="AUTH_GATE_BROKEN", reason="tenant map exists but anonymous /v1/models was not rejected")
        return result
    key = os.environ.get("OMNI_CONSUMER_API_KEY", "").strip()
    if not key:
        result.update(state="AUTH_GATE_ENABLED_NO_AUTHORIZED_PROOF",
                      reason="set OMNI_CONSUMER_API_KEY only in the execution environment to prove authorized access")
        return result
    try:
        authorized = session().get(f"{GATEWAY}/models", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        result["authorizedHttp"] = authorized.status_code
        result["state"] = "AUTH_GATE_PROVEN" if authorized.status_code == 200 else "AUTH_GATE_AUTHORIZED_REQUEST_FAILED"
    except requests.RequestException as exc:
        result.update(state="AUTH_GATE_AUTHORIZED_REQUEST_FAILED", error=error_name(exc))
    return result


def capability_summary(plan: dict[str, Any]) -> dict[str, Any]:
    rows = plan.get("providerModelCapabilityInventory") or []
    by_provider: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider") or "unknown")
        modality = str(row.get("modality") or "unknown")
        by_provider.setdefault(provider, {}).setdefault(modality, 0)
        by_provider[provider][modality] += 1
    return {"providerModelRows": len(rows), "byProvider": dict(sorted(by_provider.items())),
            "counts": plan.get("capabilityCounts") or {},
            "meaning": "inventory only; an item requires direct, routed, merged, and consumer evidence before capacity admission"}


def contract_probe(base: str, stream_model: str, tool_model: str, timeout: float,
                   auth: str = "") -> dict[str, Any]:
    """Exercise streaming and tool-bearing request preservation on one exact face."""
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    elif base.rstrip("/") == OMNI:
        key = get_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    report: dict[str, Any] = {"base": base, "stream": {}, "tools": {}}
    try:
        with session().post(f"{base.rstrip('/')}/v1/chat/completions", headers=headers, json={
            "model": stream_model, "messages": [{"role": "user", "content": "Reply with only OK."}],
            "temperature": 0, "max_tokens": 16, "stream": True,
        }, timeout=timeout, stream=True) as response:
            raw = "".join(chunk.decode("utf-8", "replace") for chunk in response.iter_content(chunk_size=4096) if chunk)[:131072]
            report["stream"] = {"http": response.status_code,
                                "hasDataFrame": any(line.startswith("data:") for line in raw.splitlines()),
                                "hasDone": any(line.strip() == "data: [DONE]" for line in raw.splitlines()),
                                "hasContent": bool(extract_chat_content({}, raw))}
    except requests.RequestException as exc:
        report["stream"] = {"error": error_name(exc)}
    tool_payload = {
        "model": tool_model,
        "messages": [{"role": "user", "content": "Call the echo tool with text set to OK."}],
        "tools": [{"type": "function", "function": {"name": "echo", "description": "Return provided text.",
                   "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}],
        "tool_choice": {"type": "function", "function": {"name": "echo"}}, "max_tokens": 64,
        "temperature": 0, "stream": False,
    }
    try:
        response = session().post(f"{base.rstrip('/')}/v1/chat/completions", headers=headers, json=tool_payload, timeout=timeout)
        parsed = plain_response(response)
        choices = parsed["json"].get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        report["tools"] = {"http": response.status_code, "hasChoices": bool(choices),
                           "hasToolCall": bool(isinstance(message, dict) and message.get("tool_calls")),
                           "hasContent": bool(isinstance(message, dict) and message.get("content"))}
    except requests.RequestException as exc:
        report["tools"] = {"error": error_name(exc)}
    report["state"] = "CONTRACT_PROVEN" if (
        report["stream"].get("http") == 200 and report["stream"].get("hasDataFrame") and
        report["stream"].get("hasContent") and report["tools"].get("http") == 200 and
        report["tools"].get("hasChoices")) else "CONTRACT_NOT_PROVEN"
    return report


def document_contract(path: pathlib.Path, must_contain: list[str]) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"path": str(path), "state": "DOCUMENT_UNAVAILABLE", "error": error_name(exc)}
    missing = [needle for needle in must_contain if needle not in text]
    return {"path": str(path), "state": "DECLARED_CONTRACT_MATCH" if not missing else "DECLARED_CONTRACT_MISMATCH",
            "missing": missing}


def app_config() -> dict[str, dict[str, str]]:
    return {
        "oioi": {"base": os.environ.get("OIOI_E2E_BASE_URL", "").rstrip("/"),
                 "token": os.environ.get("OIOI_E2E_BEARER", "")},
        "emergent": {"base": os.environ.get("EMERGENT_E2E_BASE_URL", "").rstrip("/"),
                     "token": os.environ.get("EMERGENT_E2E_BEARER", "")},
    }


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}


def consumer_apps_static() -> dict[str, Any]:
    return {
        "oioi": document_contract(OIOI_CONTRACT, ["authenticated /api/v1/films/crew-runs", "http://127.0.0.1:8190/v1/chat/completions", "video/auto"]),
        "emergent": document_contract(EMERGENT_CONTRACT, ["authenticated POST /api/pipeline/run", "http://127.0.0.1:8190/v1/chat/completions", "INFERENCE_PROVIDER=omniroute"]),
    }


def unauthenticated_consumer_checks(timeout: float) -> dict[str, Any]:
    """No-work checks: protected customer routes must reject anonymous traffic."""
    out: dict[str, Any] = {}
    for name, endpoint, payload in [
        ("oioi", "/api/v1/films/crew-runs", {"idea": "authorization probe", "target_seconds": 5, "style": "cinematic"}),
        ("emergent", "/api/pipeline/run", {"prompt": "authorization probe"}),
    ]:
        cfg = app_config()[name]
        if not cfg["base"]:
            out[name] = {"state": "NOT_CONFIGURED", "reason": f"set {name.upper()}_E2E_BASE_URL to execute"}
            continue
        try:
            response = session().post(f"{cfg['base']}{endpoint}", json=payload, timeout=timeout)
            out[name] = {"http": response.status_code,
                         "state": "ANONYMOUS_REJECTED" if response.status_code == 401 else "ANONYMOUS_NOT_REJECTED"}
        except requests.RequestException as exc:
            out[name] = {"state": "APPLICATION_UNAVAILABLE", "error": error_name(exc)}
    return out


def run_oioi_customer_path(timeout: float) -> dict[str, Any]:
    cfg = app_config()["oioi"]
    if not cfg["base"] or not cfg["token"]:
        return {"state": "NOT_RUN_CREDENTIAL_OR_BASE_MISSING", "reason": "requires OIOI_E2E_BASE_URL and OIOI_E2E_BEARER"}
    try:
        response = session().post(f"{cfg['base']}/api/v1/films/crew-runs", headers=bearer(cfg["token"]), json={
            "idea": "A 5-second acceptance-test ocean scene. Plan only; do not render clips.",
            "target_seconds": 5, "style": "cinematic", "aspect_ratio": "16:9",
        }, timeout=timeout)
        parsed = plain_response(response)
    except requests.RequestException as exc:
        return {"state": "APPLICATION_UNAVAILABLE", "error": error_name(exc)}
    body = parsed["json"]
    passed = response.status_code == 200 and bool(body.get("film_id")) and body.get("directorApproved") is True and body.get("transport") == "http://127.0.0.1:8190/v1"
    return {"http": response.status_code, "state": "OIOI_CREW_E2E_PROVEN" if passed else "OIOI_CREW_E2E_NOT_PROVEN",
            "filmIdPresent": bool(body.get("film_id")), "directorApproved": body.get("directorApproved"),
            "transport": body.get("transport"), "detail": str(body.get("detail") or body.get("error") or "")[:240]}


def run_emergent_customer_path(timeout: float, poll_timeout: float) -> dict[str, Any]:
    cfg = app_config()["emergent"]
    if not cfg["base"] or not cfg["token"]:
        return {"state": "NOT_RUN_CREDENTIAL_OR_BASE_MISSING", "reason": "requires EMERGENT_E2E_BASE_URL and EMERGENT_E2E_BEARER"}
    try:
        response = session().post(f"{cfg['base']}/api/pipeline/run", headers=bearer(cfg["token"]), json={
            "prompt": "Build a minimal accessible ocean-status dashboard with one visible heading and one button.",
            "project_name": "omniroute-e2e", "use_mock": False,
        }, timeout=timeout)
        parsed = plain_response(response)
    except requests.RequestException as exc:
        return {"state": "APPLICATION_UNAVAILABLE", "error": error_name(exc)}
    job_id = str(parsed["json"].get("job_id") or "")
    if response.status_code != 200 or not job_id:
        return {"http": response.status_code, "state": "EMERGENT_JOB_NOT_ADMITTED", "detail": str(parsed["json"])[:240]}
    deadline = time.monotonic() + poll_timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            status = session().get(f"{cfg['base']}/api/pipeline/status/{job_id}", headers=bearer(cfg["token"]), timeout=timeout)
            latest = plain_response(status)["json"]
        except requests.RequestException as exc:
            return {"http": response.status_code, "jobId": job_id, "state": "EMERGENT_STATUS_UNAVAILABLE", "error": error_name(exc)}
        if latest.get("status") in {"complete", "failed"}:
            break
        time.sleep(2)
    passed = latest.get("status") == "complete" and bool(latest.get("artifacts")) and bool(latest.get("preview_url"))
    return {"http": response.status_code, "jobId": job_id,
            "state": "EMERGENT_APP_E2E_PROVEN" if passed else "EMERGENT_APP_E2E_NOT_PROVEN",
            "jobStatus": latest.get("status"), "phase": latest.get("phase"),
            "artifactCount": len(latest.get("artifacts") or []), "previewUrlPresent": bool(latest.get("preview_url")),
            "errors": [str(x)[:160] for x in (latest.get("errors") or [])][:3]}


def release_state(report: dict[str, Any], full_execution: bool) -> str:
    if report["directPlane"].get("state") != "STABLE_CATALOG":
        return "MONETIZER_BLOCKED_OMNI_UNSTABLE"
    if report["gatewayAuth"].get("state") != "AUTH_GATE_PROVEN":
        return "MONETIZER_BLOCKED_GATEWAY_AUTH"
    if not full_execution:
        return "PREFLIGHT_ONLY_NOT_CERTIFIABLE"
    if report.get("providerSweep", {}).get("counts", {}).get("consumerLaw3", 0) < 1:
        return "MONETIZER_BLOCKED_NO_VERIFIED_OMNI_MODEL"
    if report.get("routingContracts", {}).get("gateway", {}).get("state") != "CONTRACT_PROVEN":
        return "MONETIZER_BLOCKED_GATEWAY_CONTRACT"
    apps = report.get("consumerApps", {}).get("live", {})
    if apps.get("oioi", {}).get("state") != "OIOI_CREW_E2E_PROVEN":
        return "MONETIZER_BLOCKED_OIOI_E2E"
    if apps.get("emergent", {}).get("state") != "EMERGENT_APP_E2E_PROVEN":
        return "MONETIZER_BLOCKED_EMERGENT_E2E"
    return "MONETIZER_READY"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="required before inference or customer work")
    parser.add_argument("--e2e", action="store_true", help="execute bounded provider-model and routing checks")
    parser.add_argument("--confirm-consumer-work", action="store_true", help="allow authenticated OiiOii/Emergent customer jobs")
    parser.add_argument("--confirm-video-spend", action="store_true", help="allow native Omni video proof through its existing bounded runner")
    parser.add_argument("--samples", type=int, default=3, help="read-only direct-plane catalog samples")
    parser.add_argument("--timeout", type=float, default=45, help="one inference/application request timeout")
    parser.add_argument("--consumer-timeout", type=float, default=900, help="maximum wait for the Emergent durable job")
    parser.add_argument("--lanes", type=int, default=2)
    parser.add_argument("--max-inflight", type=int, default=2)
    parser.add_argument("--min-interval", type=float, default=1.0)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--max-models-per-provider", type=int, default=0)
    args = parser.parse_args()
    if args.e2e and not args.apply:
        parser.error("--apply is required with --e2e")
    if args.confirm_consumer_work and not args.e2e:
        parser.error("--confirm-consumer-work requires --apply --e2e")
    if args.confirm_video_spend and not args.e2e:
        parser.error("--confirm-video-spend requires --apply --e2e")

    plan = graduation.build_plan(include_management=True)
    if args.max_models_per_provider:
        catalog, _ = graduation.live_catalog(graduation.no_proxy_session())
        plan["routes"] = graduation.plan_from_catalog(catalog, args.max_models_per_provider)
        plan["mode"] = "omniroute_capped_diagnostic_e2e"
    report: dict[str, Any] = {
        "schemaVersion": 1, "generatedAt": now(), "canonicalConsumerEndpoint": GATEWAY,
        "scope": "OmniRoute E2E orchestration/audit; does not operate the seat-pool graduation harness",
        "directPlane": service_stability(OMNI, args.samples, min(args.timeout, 30)),
        "gatewayAuth": consumer_auth_gate(min(args.timeout, 30)),
        "management": plan.get("management"), "capabilityInventory": capability_summary(plan),
        "consumerApps": {"declared": consumer_apps_static(), "anonymous": unauthenticated_consumer_checks(min(args.timeout, 30)), "live": {}},
        "providerSweep": {"state": "NOT_RUN"}, "routingContracts": {"state": "NOT_RUN"},
        "nativeVideo": {"state": "NOT_RUN_REQUIRES_EXPLICIT_SPEND_CONSENT"},
    }
    full_execution = False
    if args.e2e:
        if report["directPlane"]["state"] != "STABLE_CATALOG":
            report["providerSweep"] = {"state": "WITHHELD_DIRECT_PLANE_UNSTABLE"}
            report["routingContracts"] = {"state": "WITHHELD_DIRECT_PLANE_UNSTABLE"}
        else:
            full_execution = True
            report["providerSweep"] = graduation.run_chat_e2e(
                plan, args.timeout, args.timeout, args.lanes, args.max_inflight,
                args.min_interval, resume=not args.fresh)
            auth = ""
            key = os.environ.get("OMNI_CONSUMER_API_KEY", "").strip()
            if key:
                auth = f"Bearer {key}"
            report["routingContracts"] = {
                "direct": contract_probe(OMNI, "frontier", "auto/pro-coding", args.timeout),
                "gateway": contract_probe(GATEWAY, "frontier", "auto/pro-coding", args.timeout, auth),
            }
            if args.confirm_video_spend:
                report["nativeVideo"] = graduation.run_video_e2e(True, int(args.consumer_timeout), 0)
            if args.confirm_consumer_work:
                report["consumerApps"]["live"] = {
                    "oioi": run_oioi_customer_path(args.consumer_timeout),
                    "emergent": run_emergent_customer_path(args.timeout, args.consumer_timeout),
                }
            else:
                report["consumerApps"]["live"] = {
                    "oioi": {"state": "NOT_RUN_REQUIRES_CONFIRM_CONSUMER_WORK"},
                    "emergent": {"state": "NOT_RUN_REQUIRES_CONFIRM_CONSUMER_WORK"},
                }
    report["completedAt"] = now()
    report["releaseState"] = release_state(report, full_execution)
    atomic_json(OUT, report)
    print(f"output={OUT}")
    print(f"releaseState={report['releaseState']} direct={report['directPlane']['state']} auth={report['gatewayAuth']['state']} capabilityRows={report['capabilityInventory']['providerModelRows']}")
    return 0 if report["releaseState"] == "MONETIZER_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
