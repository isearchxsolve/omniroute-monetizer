#!/usr/bin/env python3
"""Canonical production graduation coordinator for the :8190 session pool.

This is deliberately an assembler, not another capture/replay implementation.
It joins the existing proven tools into the one production lineage:

  dedicated automation seat -> bounded SSO recovery -> staged capture -> exact-file Law-3 replay proof
  -> explicit ``runtime: replay`` promotion -> pure-Python registry -> :8190 hot reload

Default operation is an OFFLINE inventory.  It reads non-secret metadata only:
no CDP connection, no Chrome action, no provider request, and no service restart.
``--apply --verify-and-admit`` is intentionally one exact file at a time.  It
sends one computed replay probe and modifies that one session file only after
the verdict is REPLAY_OK.  ``--apply --capture-chat`` delegates one named seat
to tab_graduation_sweep, preserving its automation-profile guard and serial
capture discipline.

``--apply --recover-sso`` delegates one exact provider host to the bounded
fleet_sso_blueprint state machine.  It never types a password/OTP/email code,
solves a CAPTCHA, claims a signup, captures a session, or promotes capacity.

``--apply --e2e --confirm-video-spend`` is the deliberately explicit complete
fleet command.  It drives chat and video across all declared automation
profiles, persists a result after every unit, and does not call a seat
graduated until its Python runtime and the :8190 consumer contract have each
produced their required proof.  Video rendering is spend-sensitive, so the
confirmation is intentionally impossible to omit by accident.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
SECRETS = STATE / "secrets"
LEDGER = STATE / "fleet_graduation_ledger.json"
E2E_PLAN = STATE / "fleet_e2e_graduation_plan.json"
E2E_RUN = STATE / "fleet_e2e_graduation_run.json"
E2E_VIDEO_RUN = STATE / "fleet_e2e_video_graduation_run.json"
SEAT_ACCOUNTS = STATE / "video_accounts.json"
SCRATCH = STATE / "scratch"
VERIFY_PROMPT = "Reply with only the number: 41 + 17"
VERIFY_EXPECT = "58"
VIDEO_PROOF_PROMPT = "A five second abstract blue-and-gold ocean wave, no text."

sys.path.insert(0, str(HERE))
from pure_python_registry import (  # noqa: E402
    REGISTRY, admission_problem, admit, load_registry, pure_python_adapter,
    transport_for, write_registry,
)


def read_json(path: pathlib.Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def atomic_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def canonical_gate() -> dict[str, str]:
    data = read_json(STATE / "replay_check.json", {})
    rows = data.get("results", []) if isinstance(data, dict) else data
    return {str(r.get("host") or ""): str(r.get("verdict") or "")
            for r in rows if isinstance(r, dict)}


def declared_fleet() -> list[dict[str, Any]]:
    """The authoritative dedicated-seat topology, derived without Chrome/CDP."""
    data = read_json(SEAT_ACCOUNTS, {})
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for row in data.get("accounts", []) if isinstance(data, dict) else []:
        if not isinstance(row, dict) or not row.get("enabled", True):
            continue
        profile, port = str(row.get("profile") or ""), int(row.get("port") or 0)
        if not profile or not port:
            continue
        item = grouped.setdefault((profile, port), {"profile": profile, "port": port,
                                                     "labels": [], "declaredVideoProviders": []})
        if row.get("label"):
            item["labels"].append(str(row["label"]))
        if row.get("provider"):
            item["declaredVideoProviders"].append(str(row["provider"]))
    return [grouped[k] for k in sorted(grouped, key=lambda x: x[1])]


def declared_video_accounts() -> list[dict[str, Any]]:
    """Return every enabled video account with its exact configured project URL."""
    data = read_json(SEAT_ACCOUNTS, {})
    out: list[dict[str, Any]] = []
    for row in data.get("accounts", []) if isinstance(data, dict) else []:
        if not isinstance(row, dict) or not row.get("enabled", True):
            continue
        if not all(row.get(k) for k in ("label", "provider", "port", "profile", "url")):
            continue
        item = dict(row)
        item["port"] = int(item["port"])
        item["host"] = urllib.parse.urlparse(str(item["url"])).hostname or ""
        if item["host"]:
            out.append(item)
    return sorted(out, key=lambda r: (int(r["port"]), str(r["label"])))


def e2e_plan() -> dict[str, Any]:
    """All-profile production plan.  Deliberately no CDP/network/provider action."""
    fleet = declared_fleet()
    return {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "all_profiles_static_e2e_plan_no_browser_no_provider_request",
        "consumerContract": "http://127.0.0.1:8190/v1",
        "fleet": fleet,
        "serialExecutionOrder": [
            "for each profile/port: bounded SSO recovery per exact host",
            "refresh/read manifest for that same dedicated seat",
            "capture one eligible chat surface",
            "read that exact unit's Law-3 proof and admit only REPLAY_OK",
            "continue to the next seat after spacing; never parallelize one host",
            "run video submit-poll-result capture and Python graduation with explicit spend confirmation",
            "run pinned :8190 consumer probes and publish provider x model-family capacity",
        ],
        "whatThisDoesNotDo": [
            "open Chrome", "drive SSO", "capture", "replay", "spend video credits",
            "admit a seat", "claim capacity",
        ],
    }


def inventory() -> dict[str, Any]:
    """Build a secret-free all-artifact ledger.  Does not open a browser or network socket."""
    registry = load_registry()
    admitted = {str(e.get("sessionFile")): e for e in registry["entries"]
                if e.get("state") == "ADMITTED"}
    gate = canonical_gate()
    rows: list[dict[str, Any]] = []
    for path in sorted(SECRETS.glob("session_*.json")):
        raw = read_json(path, {})
        if not isinstance(raw, dict):
            rows.append({"sessionFile": path.name, "state": "CORRUPT_ARTIFACT"})
            continue
        host = str(raw.get("host") or "")
        modality = str(raw.get("modality") or ("video" if raw.get("recorded_job") else "chat"))
        adapter = pure_python_adapter(raw)
        issue = admission_problem(raw)
        existing = admitted.get(path.name)
        if existing and modality == "chat":
            state = "ADMITTED_TO_8190_PURE_PYTHON"
            next_action = "local_endpoint_probe_when_operator_chooses"
        elif existing and modality == "video":
            state = "ADMITTED_TO_8190_PURE_PYTHON"
            next_action = "pinned :8190 video consumer proof or periodic health audit"
        elif modality == "video":
            state = "VIDEO_PROOF_REQUIRED"
            next_action = "master --apply --e2e --confirm-video-spend captures, proves, and admits exactly this seat"
        elif issue:
            state = "NOT_PURE_PYTHON_ELIGIBLE"
            next_action = issue
        else:
            state = "LAW3_REPLAY_PROOF_REQUIRED"
            next_action = "apply --verify-and-admit <sessionFile> (one provider request)"
        rows.append({
            "sessionFile": path.name, "host": host, "modality": modality,
            "transport": transport_for(raw), "runtime": str(raw.get("runtime") or ""),
            "adapter": adapter or "", "legacyHostReplayVerdict": gate.get(host, ""),
            "registryState": str((existing or {}).get("state") or ""),
            "state": state, "nextAction": next_action,
        })
    counts = Counter(row["state"] for row in rows)
    return {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "offline_inventory_no_browser_no_provider_request",
        "consumerContract": "http://127.0.0.1:8190/v1",
        "whatThisProves": "artifact and admission structure only",
        "whatThisDoesNotProve": [
            "provider signup", "current account entitlement", "replay health unless exact-file proof exists",
            "video render success", "consumer E2E success", "provider-by-model capacity",
        ],
        "summary": {"sessionArtifacts": len(rows), "byState": dict(sorted(counts.items())),
                    "admittedChatFiles": sum(1 for r in rows if r["state"] == "ADMITTED_TO_8190_PURE_PYTHON")},
        "rows": rows,
    }


def exact_session(name: str) -> pathlib.Path:
    candidate = pathlib.Path(name).name
    if candidate != name or not candidate.startswith("session_") or not candidate.endswith(".json"):
        raise SystemExit("--verify-and-admit requires one bare session_*.json filename")
    path = SECRETS / candidate
    if not path.is_file():
        raise SystemExit(f"session artifact not found: {candidate}")
    return path


def read_single_verdict(path: pathlib.Path) -> tuple[str, str]:
    data = read_json(path, {})
    rows = data.get("results", []) if isinstance(data, dict) else []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        return "NO_EXACT_VERDICT", "replay report did not contain exactly one row"
    return str(rows[0].get("verdict") or ""), str(rows[0].get("detail") or "")[:200]


def verify_and_admit(session_path: pathlib.Path) -> None:
    raw = read_json(session_path, {})
    if not isinstance(raw, dict):
        raise SystemExit("session artifact is not valid JSON")
    modality = str(raw.get("modality") or ("video" if raw.get("recorded_job") else "chat"))
    if modality != "chat":
        raise SystemExit("video requires its separate spend-gated submit-poll-result graduation; not run here")
    problem = admission_problem(raw)
    if problem:
        raise SystemExit(f"refusing pure-Python admission: {problem}")
    report = SCRATCH / f"fleet_graduation_{session_path.stem}.json"
    cmd = [sys.executable, str(HERE / "replay_check.py"), "--only", session_path.name,
           "--prompt", VERIFY_PROMPT, "--expect", VERIFY_EXPECT, "--out", str(report)]
    completed = subprocess.run(cmd, cwd=ROOT, check=False)
    verdict, detail = read_single_verdict(report)
    if completed.returncode != 0 or verdict != "REPLAY_OK":
        raise SystemExit(f"not admitted: {verdict or 'NO_VERDICT'} {detail}")
    # Promotion is a state transition after, never before, the exact-file proof.
    raw["runtime"] = "replay"
    raw["graduation"] = {
        "kind": "pure_python_replay",
        "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt": VERIFY_PROMPT,
        "expect": VERIFY_EXPECT,
        "verdict": verdict,
        "report": str(report.relative_to(ROOT)),
    }
    atomic_json(session_path, raw)
    registry = load_registry()
    entry = admit(registry, session_file=session_path.name, host=str(raw.get("host") or ""),
                  modality="chat", adapter=str(pure_python_adapter(raw)), verification={
                      "kind": "Law-3 computed replay", "prompt": VERIFY_PROMPT,
                      "expect": VERIFY_EXPECT, "verdict": verdict,
                      "report": str(report.relative_to(ROOT)),
                  })
    write_registry(registry)
    print(f"ADMITTED {entry['sessionFile']} -> {entry['adapter']} (shim hot-reloads; no restart)")


def capture_chat(port: int, site: str) -> None:
    """Delegate exactly one guarded capture/replay unit; promotion remains explicit."""
    cmd = [sys.executable, str(HERE / "tab_graduation_sweep.py"), "--port", str(port),
           "--execute", "--site", site]
    rc = subprocess.run(cmd, cwd=ROOT, check=False).returncode
    if rc:
        raise SystemExit(f"capture unit failed with exit code {rc}; no promotion performed")
    print("capture/replay unit completed. Inspect the exact new session file, then run --apply --verify-and-admit.")


def _admit_from_existing_proof(path: pathlib.Path, proof: pathlib.Path) -> str:
    """Promote a fresh capture using its existing one-request scratch verdict."""
    raw = read_json(path, {})
    verdict, detail = read_single_verdict(proof)
    if not isinstance(raw, dict) or verdict != "REPLAY_OK":
        raise RuntimeError(f"proof not promotable: {verdict or 'NO_VERDICT'} {detail}")
    problem = admission_problem(raw)
    if problem:
        raise RuntimeError(problem)
    raw["runtime"] = "replay"
    raw["graduation"] = {"kind": "pure_python_replay", "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "prompt": VERIFY_PROMPT, "expect": VERIFY_EXPECT, "verdict": verdict,
                          "report": str(proof.relative_to(ROOT))}
    atomic_json(path, raw)
    registry = load_registry()
    entry = admit(registry, session_file=path.name, host=str(raw.get("host") or ""), modality="chat",
                  adapter=str(pure_python_adapter(raw)), verification={"kind": "Law-3 computed replay",
                  "prompt": VERIFY_PROMPT, "expect": VERIFY_EXPECT, "verdict": verdict,
                  "report": str(proof.relative_to(ROOT))})
    write_registry(registry)
    return str(entry["adapter"])


def _video_session_path(host: str, label: str) -> pathlib.Path:
    stem = f"session_{host.replace('.', '_').replace('/', '_')}"
    return SECRETS / f"{stem}_{label}.json"


def _is_video_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def _video_python_client(path: pathlib.Path, raw: dict[str, Any]) -> Any:
    """Select a browser-independent runtime for one freshly captured video file."""
    # A captured submit->poll->result sequence is the most exact source of
    # truth.  It intentionally wins over legacy `api.kind=flow`, whose old
    # implementation delegates to :8189 and is therefore not graduation.
    if raw.get("recorded_job"):
        from video_universal_replay import VideoUniversalSessionClient
        return VideoUniversalSessionClient(path)
    kind = str((raw.get("api") or {}).get("kind") or "")
    if kind == "digen":
        from digen_session_replay import DigenSessionClient
        return DigenSessionClient(path)
    if kind == "rtst":
        from rtst_api_client import RtstApiClient
        return RtstApiClient(path)
    raise RuntimeError("no captured video job and no registered pure-Python video API adapter")


def verify_video_and_admit(path: pathlib.Path) -> dict[str, Any]:
    """Spend one bounded Python render and admit the exact file only on URL proof."""
    raw = read_json(path, {})
    if not isinstance(raw, dict):
        raise RuntimeError("invalid video session artifact")
    if str(raw.get("modality") or "video") != "video":
        raise RuntimeError("artifact is not a video seat")
    problem = admission_problem(raw)
    if problem:
        raise RuntimeError(problem)
    job = raw.get("recorded_job")
    if isinstance(job, dict) and job.get("result_correlated") is not True:
        raise RuntimeError("capture lacks correlated submit-poll-result proof")
    result = _video_python_client(path, raw).chat([
        {"role": "user", "content": VIDEO_PROOF_PROMPT},
    ])
    video_url = result.get("text") if isinstance(result, dict) else None
    if not _is_video_url(video_url):
        raise RuntimeError("Python video adapter returned no result URL")
    raw["runtime"] = "replay"
    raw["graduation"] = {
        "kind": "pure_python_video_submit_poll_result",
        "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt": VIDEO_PROOF_PROMPT,
        "resultUrlObserved": True,
        "adapter": pure_python_adapter(raw),
    }
    atomic_json(path, raw)
    registry = load_registry()
    entry = admit(registry, session_file=path.name, host=str(raw.get("host") or ""), modality="video",
                  adapter=str(pure_python_adapter(raw)), verification={
                      "kind": "Python submit-poll-result", "resultUrlObserved": True,
                      "prompt": VIDEO_PROOF_PROMPT,
                  })
    write_registry(registry)
    return {"sessionFile": path.name, "host": entry["host"], "adapter": entry["adapter"],
            "state": "ADMITTED_TO_8190_PURE_PYTHON", "resultUrlObserved": True}


def capture_and_graduate_video(account: dict[str, Any], job_wait: float, sso_budget: float) -> dict[str, Any]:
    """One seat: exact-host SSO -> project -> capture -> Python render -> admission."""
    host, label = str(account["host"]), str(account["label"])
    path = _video_session_path(host, label)
    sso_rc = subprocess.run([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port",
                             str(account["port"]), "--drive", "--include-video", "--host-exact", host,
                             "--budget", str(sso_budget)], cwd=ROOT, check=False).returncode
    if sso_rc:
        return {"profile": account["profile"], "port": account["port"], "label": label,
                "provider": account["provider"], "host": host, "ssoRc": sso_rc,
                "state": "NOT_ADMITTED", "detail": "bounded video SSO recovery failed; capture not attempted"}
    started = time.time()
    cmd = [sys.executable, str(HERE / "capture_video_job_cdp.py"), "--port", str(account["port"]),
           "--match", str(account["url"]), "--url", str(account["url"]), "--host", host,
           "--seat", label, "--job-wait", str(job_wait)]
    rc = subprocess.run(cmd, cwd=ROOT, check=False).returncode
    row: dict[str, Any] = {"profile": account["profile"], "port": account["port"], "label": label,
                           "provider": account["provider"], "host": host, "ssoRc": sso_rc, "captureRc": rc,
                           "state": "NOT_ADMITTED"}
    if rc != 0 or not path.is_file() or path.stat().st_mtime < started - 2:
        row["detail"] = "video capture left no fresh correlated session artifact"
        return row
    try:
        row.update(verify_video_and_admit(path))
    except Exception as exc:
        row["detail"] = f"{type(exc).__name__}: {exc}"[:260]
    return row


def _http_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 30.0) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return int(exc.code), json.loads(exc.read().decode("utf-8"))
        except Exception:
            return int(exc.code), {}


def consumer_video_probe(host: str, timeout: float = 1900.0) -> dict[str, Any]:
    """Final pinned :8190 proof; submit once and poll its durable job receipt."""
    key = f"fleet-graduation-{host.replace('.', '-')}-{uuid.uuid4().hex}"
    status, receipt = _http_json("http://127.0.0.1:8190/v1/chat/completions", {
        "model": f"video/{host}/auto", "messages": [{"role": "user", "content": VIDEO_PROOF_PROMPT}],
        "video": {"job_key": key},
    }, timeout=40)
    row: dict[str, Any] = {"host": host, "model": f"video/{host}/auto", "submitHttp": status,
                           "state": "CONSUMER_NOT_PROVEN"}
    job_id = str(receipt.get("id") or receipt.get("job_id") or "")
    if status not in (200, 202) or not job_id:
        row["detail"] = str(receipt.get("error") or receipt.get("message") or "missing receipt")[:180]
        return row
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = _http_json(f"http://127.0.0.1:8190/v1/video/jobs/{job_id}", timeout=30)
        state = str(body.get("status") or "").lower()
        if state in {"completed", "succeeded", "success"}:
            url = body.get("result_url") or body.get("video_url") or body.get("url")
            row.update(state="CONSUMER_E2E_PROVEN", resultUrlObserved=_is_video_url(url), pollHttp=status)
            if not row["resultUrlObserved"]:
                row["state"] = "CONSUMER_RESULT_URL_MISSING"
            return row
        if state in {"failed", "cancelled", "canceled"}:
            row.update(state="CONSUMER_FAILED", pollHttp=status, detail=str(body.get("error") or state)[:180])
            return row
        time.sleep(5)
    row["state"] = "CONSUMER_TIMEOUT"
    return row


def consumer_chat_probe(host: str) -> dict[str, Any]:
    """Pinned OpenAI-compatible Law-3 proof through the actual consumer face."""
    status, body = _http_json("http://127.0.0.1:8190/v1/chat/completions", {
        "model": f"{host}/auto",
        "messages": [{"role": "user", "content": VERIFY_PROMPT}],
    }, timeout=90)
    content = ""
    try:
        content = str(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        pass
    return {"host": host, "model": f"{host}/auto", "http": status,
            "state": "CONSUMER_E2E_PROVEN" if status == 200 and content.strip() == VERIFY_EXPECT
            else "CONSUMER_NOT_PROVEN", "computedAnswerObserved": content.strip() == VERIFY_EXPECT}


def e2e_chat_consumer_proofs() -> None:
    """Append one pinned consumer proof per admitted chat host to the durable run."""
    run = read_json(E2E_RUN, {})
    if not isinstance(run, dict):
        run = {}
    registry = load_registry()
    hosts = sorted({str(e.get("host") or "") for e in registry.get("entries", [])
                    if isinstance(e, dict) and e.get("state") == "ADMITTED"
                    and e.get("modality") == "chat" and e.get("host")})
    run["consumerProofs"] = [consumer_chat_probe(host) for host in hosts]
    atomic_json(E2E_RUN, run)


def e2e_video_apply(job_wait: float, sso_budget: float) -> None:
    """Serial complete video lane.  Every row is durable before the next spends."""
    run = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "mode": "serial_all_profile_video_capture_python_graduation_consumer_proof",
           "consumerContract": "http://127.0.0.1:8190/v1", "seats": [], "consumerProofs": []}
    for account in declared_video_accounts():
        row = capture_and_graduate_video(account, job_wait, sso_budget)
        run["seats"].append(row)
        atomic_json(E2E_VIDEO_RUN, run)
        time.sleep(4)
    # A pin selects a provider host, not an account label.  Prove every host
    # with at least one exact-file graduation, while the seat rows remain the
    # capacity source of truth.
    for host in sorted({str(r["host"]) for r in run["seats"]
                        if r.get("state") == "ADMITTED_TO_8190_PURE_PYTHON"}):
        run["consumerProofs"].append(consumer_video_probe(host))
        atomic_json(E2E_VIDEO_RUN, run)
    print(f"all-profile video E2E complete: {E2E_VIDEO_RUN.name}")


def e2e_apply(sso_budget: float, capture_wait: float, limit: int, video_job_wait: float) -> None:
    """The literal complete master sequence requested by the operator."""
    # Child video clients use this established explicit spend gate.  It is set
    # only inside the command that also required --confirm-video-spend.
    prior = os.environ.get("OMNI_VIDEO_CONFIRM_SPEND")
    os.environ["OMNI_VIDEO_CONFIRM_SPEND"] = "1"
    try:
        e2e_chat_apply(sso_budget, capture_wait, limit)
        e2e_chat_consumer_proofs()
        e2e_video_apply(video_job_wait, sso_budget)
    finally:
        if prior is None:
            os.environ.pop("OMNI_VIDEO_CONFIRM_SPEND", None)
        else:
            os.environ["OMNI_VIDEO_CONFIRM_SPEND"] = prior


def e2e_chat_apply(sso_budget: float, capture_wait: float, limit: int) -> None:
    """Serial all-profile chat lane: SSO -> manifest -> capture/replay -> exact admission."""
    from tab_graduation_sweep import scratch_report, session_slug
    run = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "mode": "serial_all_profile_chat_graduation", "consumerContract": "http://127.0.0.1:8190/v1",
           "video": "not triggered; separate explicit spend-gated graduation", "profiles": []}
    left = limit or 10**9
    for seat in declared_fleet():
        port, profile = int(seat["port"]), str(seat["profile"])
        unit = {"profile": profile, "port": port, "sso": [], "captures": []}
        # Plan gives current dedicated-seat hosts. Mandate (operator, 2026-08-31):
        # every host gets its bounded SSO attempt unless the live probe
        # positively says signed-in -- a probe ERROR (signedOut None, flaky
        # hydration) must NEVER cause a silent skip. The state machine is
        # probe-first: signed-in rows terminate as EXISTING_ACCOUNT without
        # a single click, so driving them is safe and honest.
        subprocess.run([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port)], cwd=ROOT, check=False)
        plan = read_json(STATE / f"fleet_blueprint_plan_{port}.json", {})
        for row in plan.get("hosts", []) if isinstance(plan, dict) else []:
            if row.get("host") and row.get("signedOut") is not False:
                host = str(row["host"])
                rc = subprocess.run([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port),
                                     "--drive", "--host-exact", host, "--budget", str(sso_budget)], cwd=ROOT, check=False).returncode
                unit["sso"].append({"host": host, "rc": rc,
                                    "probe": str(row.get("signedOut"))})
        # The harness is the navigation + bounded-SSO layer for tabs that are
        # authenticated but not yet sitting on a capture surface.  Its default
        # post-apply readiness audit is load-bearing: without it a just-signed-
        # in site remains stale SKIP_NOT_AUTHENTICATED in the next manifest.
        harness_rc = subprocess.run([sys.executable, str(HERE / "harness_all_tabs.py"), "--port", str(port),
                                     "--apply", "--wait", "10", "--budget", str(max(120, int(sso_budget)))],
                                    cwd=ROOT, check=False).returncode
        unit["harnessRc"] = harness_rc
        manifest_path = STATE / f"fleet_e2e_manifest_{port}.json"
        subprocess.run([sys.executable, str(HERE / "tab_graduation_sweep.py"), "--port", str(port),
                        "--json", str(manifest_path)], cwd=ROOT, check=False)
        manifest = read_json(manifest_path, {})
        seen: set[str] = set()
        for tab in manifest.get("tabs", []) if isinstance(manifest, dict) else []:
            if left <= 0 or tab.get("classification") != "ELIGIBLE_CAPTURE":
                continue
            site = str(tab.get("knownSite") or "")
            if not site or site in seen:
                continue
            seen.add(site); started = time.time()
            rc = subprocess.run([sys.executable, str(HERE / "tab_graduation_sweep.py"), "--port", str(port),
                                 "--execute", "--site", site, "--wait", str(capture_wait)], cwd=ROOT, check=False).returncode
            expected = SECRETS / f"session_{session_slug(site)}.json"
            item = {"site": site, "captureRc": rc, "state": "NOT_ADMITTED"}
            if rc == 0 and expected.exists() and expected.stat().st_mtime >= started - 2:
                try:
                    item.update(state="ADMITTED_TO_8190_PURE_PYTHON", sessionFile=expected.name,
                                adapter=_admit_from_existing_proof(expected, scratch_report(site)))
                except Exception as exc:
                    item["detail"] = f"{type(exc).__name__}: {exc}"[:220]
            else:
                item["detail"] = "capture did not leave a fresh exact session artifact"
            unit["captures"].append(item); left -= 1
            atomic_json(E2E_RUN, {**run, "profiles": run["profiles"] + [unit]})
            time.sleep(4)
        run["profiles"].append(unit); atomic_json(E2E_RUN, run)
    print(f"all-profile chat E2E complete: {E2E_RUN.name}")


def recover_sso(port: int, host: str, budget: float) -> None:
    """Delegate one exact dedicated-seat SSO unit; no capture or promotion follows it."""
    exact = host.strip().lower()
    if not exact or "://" in exact or "/" in exact or "?" in exact:
        raise SystemExit("--recover-sso requires one bare exact host, for example chat.qwen.ai")
    cmd = [sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port),
           "--drive", "--host-exact", exact, "--budget", str(budget)]
    rc = subprocess.run(cmd, cwd=ROOT, check=False).returncode
    if rc:
        raise SystemExit(f"SSO recovery unit failed with exit code {rc}; no capture or promotion performed")
    print("SSO recovery completed as surface evidence only. Run a separate guarded capture unit after reviewing its report.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="required before any provider request or session-file mutation")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--verify-and-admit", metavar="SESSION_FILE", help="one exact chat session_*.json")
    group.add_argument("--capture-chat", metavar="SITE", help="one exact named chat site via the guarded sweep")
    group.add_argument("--recover-sso", metavar="HOST", help="one exact provider host via bounded SSO recovery")
    group.add_argument("--e2e-plan", action="store_true",
                       help="write the all-profile/all-seat production plan; no Chrome or network")
    group.add_argument("--e2e-chat", action="store_true",
                       help="serial SSO -> capture -> proof -> pure-Python admission across every declared profile; video excluded")
    group.add_argument("--e2e", action="store_true",
                       help="COMPLETE all-profile master: SSO, chat capture/proof/admission, video capture/Python render/admission, and pinned :8190 video proof")
    ap.add_argument("--port", type=int, default=9222, help="dedicated automation CDP port for capture or SSO recovery")
    ap.add_argument("--sso-budget", type=float, default=240.0,
                    help="wall-clock seconds for one --recover-sso host")
    ap.add_argument("--capture-wait", type=float, default=25.0, help="per-seat capture wait in --e2e-chat")
    ap.add_argument("--limit", type=int, default=0, help="cap chat seats in --e2e-chat (0 = all)")
    ap.add_argument("--video-job-wait", type=float, default=420.0,
                    help="seconds to record one browser video job's submit -> poll -> result sequence")
    ap.add_argument("--confirm-video-spend", action="store_true",
                    help="required with --apply --e2e; acknowledges real video renders in capture, Python proof, and pinned :8190 proof")
    args = ap.parse_args()
    if (args.verify_and_admit or args.capture_chat or args.recover_sso or args.e2e_chat or args.e2e) and not args.apply:
        ap.error("--apply is required: these operations send a provider request and/or change an admission")
    if args.e2e and not args.confirm_video_spend:
        ap.error("--apply --e2e requires --confirm-video-spend because it deliberately renders real videos")
    if args.verify_and_admit:
        verify_and_admit(exact_session(args.verify_and_admit))
    elif args.capture_chat:
        capture_chat(args.port, args.capture_chat)
    elif args.recover_sso:
        recover_sso(args.port, args.recover_sso, args.sso_budget)
    elif args.e2e_plan:
        plan = e2e_plan()
        atomic_json(E2E_PLAN, plan)
        print(f"all-profile E2E plan: {E2E_PLAN.name}; seats={len(plan['fleet'])}; "
              f"ports={[x['port'] for x in plan['fleet']]}")
    elif args.e2e_chat:
        e2e_chat_apply(args.sso_budget, args.capture_wait, args.limit)
    elif args.e2e:
        e2e_apply(args.sso_budget, args.capture_wait, args.limit, args.video_job_wait)
    ledger = inventory()
    atomic_json(LEDGER, ledger)
    summary = ledger["summary"]
    print(f"ledger: {LEDGER.name}; artifacts={summary['sessionArtifacts']}; "
          f"admittedChatFiles={summary['admittedChatFiles']}; states={summary['byState']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
