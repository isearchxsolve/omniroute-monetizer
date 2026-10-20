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

``--apply --e2e-video --confirm-video-spend`` is the resumable video-only
continuation.  It reuses completed chat graduation evidence and runs every
declared video seat without re-driving chat tabs or re-spending chat probes.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
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
ATTEMPTS = STATE / "graduation_attempts"


def checked_proof(path: pathlib.Path, artifact: pathlib.Path, attempt_id: str) -> dict[str, Any]:
    """Fail closed on legacy, stale, foreign, mutated or merely labelled evidence."""
    data = read_json(path, {})
    rows = data.get("results", []) if isinstance(data, dict) else []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError("NO_EXACT_VERDICT")
    row = rows[0]
    raw = read_json(artifact, {})
    if not isinstance(raw, dict):
        raise RuntimeError("INVALID_ARTIFACT_SCHEMA")
    verification = row.get("verification") or {}
    if not isinstance(verification, dict):
        raise RuntimeError("INVALID_VERIFICATION_SCHEMA")
    if not attempt_id or row.get("attemptId") != attempt_id:
        raise RuntimeError("PROOF_ATTEMPT_MISMATCH")
    if row.get("file") != artifact.name or row.get("host") != raw.get("host"):
        raise RuntimeError("PROOF_ARTIFACT_IDENTITY_MISMATCH")
    if row.get("artifactSha256") != hashlib.sha256(artifact.read_bytes()).hexdigest():
        raise RuntimeError("PROOF_ARTIFACT_CHANGED")
    if (row.get("verdict") != "REPLAY_OK" or verification.get("version") != "terminal-exact-v1"
            or verification.get("exactAnswer") is not True
            or verification.get("prompt") != VERIFY_PROMPT or verification.get("expected") != VERIFY_EXPECT):
        raise RuntimeError("TERMINAL_EXACT_ANSWER_NOT_PROVEN")
    return row


def attempt_environment(attempt_id: str) -> dict[str, str]:
    return {**os.environ, "OMNI_GRADUATION_ATTEMPT_ID": attempt_id,
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def save_attempt(attempt_id: str, **fields: Any) -> None:
    """A separate receipt per attempt; no provider bodies or credentials."""
    if not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
        raise RuntimeError("INVALID_ATTEMPT_ID")
    path = ATTEMPTS / f"{attempt_id}.json"
    current = read_json(path, {})
    events = current.get("events", []) + [{"stage": fields.get("stage"), "state": fields.get("state"),
                                           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]
    atomic_json(path, {**current, **fields, "attemptId": attempt_id,
                       "events": events,
                       "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


@contextlib.contextmanager
def controller_lock():
    """OS-held lock releases on crash; no PID guesses, process killing or stale takeover."""
    path = STATE / "fleet_graduation.owner.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SystemExit("another graduation controller owns this run") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

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
                    "admittedSessionFiles": sum(1 for r in rows if r["state"] == "ADMITTED_TO_8190_PURE_PYTHON"),
                    "admittedChatFiles": sum(1 for r in rows if r["state"] == "ADMITTED_TO_8190_PURE_PYTHON" and r.get("modality") == "chat"),
                    "admittedVideoFiles": sum(1 for r in rows if r["state"] == "ADMITTED_TO_8190_PURE_PYTHON" and r.get("modality") == "video")},
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
    attempt_id = uuid.uuid4().hex
    report = ATTEMPTS / f"{attempt_id}.replay.json"
    save_attempt(attempt_id, stage="replay", state="RUNNING", sessionFile=session_path.name)
    cmd = [sys.executable, str(HERE / "replay_check.py"), "--only", session_path.name,
           "--prompt", VERIFY_PROMPT, "--expect", VERIFY_EXPECT, "--out", str(report)]
    rc = run_bounded_child(cmd, timeout=180, env=attempt_environment(attempt_id))
    if rc != 0:
        save_attempt(attempt_id, stage="replay", state="BLOCKED", reason="CHILD_FAILED_OR_TIMED_OUT")
        raise SystemExit("not admitted: replay child failed or timed out")
    try:
        proof = checked_proof(report, session_path, attempt_id)
    except RuntimeError as exc:
        save_attempt(attempt_id, stage="replay", state="BLOCKED", reason=str(exc))
        raise SystemExit(f"not admitted: {exc}") from exc
    verdict = proof["verdict"]
    # Replay clients can persist rotated credentials. Never overwrite those with
    # the pre-call snapshot while adding admission metadata.
    raw = read_json(session_path, {})
    # Promotion is a state transition after, never before, the exact-file proof.
    raw["runtime"] = "replay"
    # A staged artifact carries status.alive=False (pending_replay_verification), which
    # the pool reads as flagged_dead and refuses to dispatch. The proof just passed, so
    # the staging quarantine is lifted in the same transition -- leaving it False would
    # admit a file the pool can never serve.
    if raw.get("status", {}).get("alive") is False:
        raw["status"] = {"alive": True,
                         "harvested_at": raw.get("status", {}).get("harvested_at"),
                         "reason": "staging_quarantine_lifted_after_law3_proof"}
    raw["graduation"] = {
        "kind": "pure_python_replay",
        "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt": VERIFY_PROMPT,
        "expect": VERIFY_EXPECT,
        "verdict": verdict,
        "report": str(report.relative_to(ROOT)),
        "attemptId": attempt_id,
        "artifactSha256": proof["artifactSha256"],
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
    save_attempt(attempt_id, stage="pool_admission", state="ADMITTED_CONSUMER_NOT_YET_PROVEN",
                 artifactSha256=proof["artifactSha256"], report=str(report.relative_to(ROOT)))
    print(f"ADMITTED {entry['sessionFile']} -> {entry['adapter']} (shim hot-reloads; no restart)")


def capture_chat(port: int, site: str) -> None:
    """Delegate exactly one guarded capture/replay unit; promotion remains explicit."""
    cmd = [sys.executable, str(HERE / "tab_graduation_sweep.py"), "--port", str(port),
           "--execute", "--site", site]
    rc = run_bounded_child(cmd, timeout=300)
    if rc:
        raise SystemExit(f"capture unit failed with exit code {rc}; no promotion performed")
    print("capture/replay unit completed. Inspect the exact new session file, then run --apply --verify-and-admit.")


def _admit_from_existing_proof(path: pathlib.Path, proof: pathlib.Path, attempt_id: str = "") -> str:
    """Promote a fresh capture using its existing one-request scratch verdict."""
    raw = read_json(path, {})
    evidence = checked_proof(proof, path, attempt_id)
    verdict = evidence["verdict"]
    # Preserve checked evidence before another unit replaces the scratch report.
    retained = ATTEMPTS / f"{attempt_id}.replay.json"
    atomic_json(retained, read_json(proof, {}))
    proof = retained
    problem = admission_problem(raw)
    if problem:
        raise RuntimeError(problem)
    raw["runtime"] = "replay"
    if raw.get("status", {}).get("alive") is False:
        raw["status"] = {**raw["status"], "alive": True, "reason": "exact_attempt_replay_verified"}
    raw["graduation"] = {"kind": "pure_python_replay", "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "prompt": VERIFY_PROMPT, "expect": VERIFY_EXPECT, "verdict": verdict,
                          "report": str(proof.relative_to(ROOT)), "attemptId": attempt_id,
                          "artifactSha256": evidence["artifactSha256"]}
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


def verify_media_delivery(url: str) -> dict[str, Any]:
    """Verify actual bounded delivery and video decoding metadata, never just a URL."""
    probe = shutil.which("ffprobe")
    if not probe or not _is_video_url(url):
        raise RuntimeError("MEDIA_VERIFIER_OR_URL_UNAVAILABLE")
    digest, size, deadline = hashlib.sha256(), 0, time.monotonic() + 60
    with tempfile.TemporaryDirectory(prefix="graduation-media-") as directory:
        path = pathlib.Path(directory) / "artifact"
        with urllib.request.urlopen(url, timeout=15) as response, path.open("wb") as output:
            if response.status != 200:
                raise RuntimeError("MEDIA_DOWNLOAD_NOT_SUCCESSFUL")
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > 64 * 1024 * 1024 or time.monotonic() > deadline:
                    raise RuntimeError("MEDIA_DELIVERY_LIMIT_EXCEEDED")
                output.write(chunk); digest.update(chunk)
        completed = subprocess.run([probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                   capture_output=True, encoding="utf-8", errors="replace", timeout=20, check=False)
        try:
            metadata = json.loads(completed.stdout)
            duration = float(metadata.get("format", {}).get("duration", 0))
        except (ValueError, AttributeError):
            raise RuntimeError("MEDIA_METADATA_INVALID") from None
        video = any(stream.get("codec_type") == "video" and stream.get("width", 0) > 0
                    and stream.get("height", 0) > 0 for stream in metadata.get("streams", []) if isinstance(stream, dict))
        if completed.returncode or not video or not (0 < duration < float("inf")):
            raise RuntimeError("DELIVERED_VIDEO_NOT_VERIFIED")
    return {"sha256": digest.hexdigest(), "bytes": size, "durationSeconds": duration,
            "videoStreamVerified": True}


def run_bounded_child(command: list[str], timeout: float, env: dict[str, str] | None = None) -> int | None:
    """Run one generated child command; on timeout stop *only that child tree*.

    ``fleet_sso_blueprint`` has its own deadline, but the parent is the final
    safety owner.  Without this second deadline a wedged CDP child can strand
    the all-profile master before it has persisted a terminal seat row.
    """
    proc = subprocess.Popen(command, cwd=ROOT,
                            env=env or {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    try:
        return proc.wait(timeout=max(1.0, timeout))
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            # The command is constructed in this module and is either the
            # bounded SSO blueprint or the bounded video capture helper.
            # /T is essential because a venv launcher owns the actual Python
            # interpreter; it never targets Chrome or an unrelated process.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        return None


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


def verify_video_and_admit(path: pathlib.Path, attempt_id: str | None = None) -> dict[str, Any]:
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
    if not shutil.which("ffprobe"):
        raise RuntimeError("MEDIA_VERIFIER_UNAVAILABLE_BEFORE_RENDER")
    result = _video_python_client(path, raw).chat([
        {"role": "user", "content": VIDEO_PROOF_PROMPT},
    ])
    video_url = result.get("text") if isinstance(result, dict) else None
    if not _is_video_url(video_url):
        raise RuntimeError("Python video adapter returned no result URL")
    media = verify_media_delivery(video_url)
    raw = read_json(path, {})
    attempt_id = attempt_id or uuid.uuid4().hex
    raw["runtime"] = "replay"
    raw["graduation"] = {
        "kind": "pure_python_video_submit_poll_result",
        "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt": VIDEO_PROOF_PROMPT,
        "resultUrlObserved": True,
        "adapter": pure_python_adapter(raw),
        "mediaProof": media,
        "attemptId": attempt_id,
    }
    atomic_json(path, raw)
    registry = load_registry()
    entry = admit(registry, session_file=path.name, host=str(raw.get("host") or ""), modality="video",
                  adapter=str(pure_python_adapter(raw)), verification={
                      "kind": "Python submit-poll-result", "resultUrlObserved": True,
                      "prompt": VIDEO_PROOF_PROMPT, "mediaProof": media,
                  })
    write_registry(registry)
    return {"sessionFile": path.name, "host": entry["host"], "adapter": entry["adapter"],
            "state": "ADMITTED_TO_8190_PURE_PYTHON", "resultUrlObserved": True}


def capture_and_graduate_video(account: dict[str, Any], job_wait: float, sso_budget: float) -> dict[str, Any]:
    attempt_id = uuid.uuid4().hex
    save_attempt(attempt_id, stage="login", state="RUNNING", host=str(account["host"]),
                 profile=str(account["profile"]), seat=str(account["label"]))
    try:
        row = _capture_and_graduate_video(account, job_wait, sso_budget, attempt_id)
    except Exception as exc:
        save_attempt(attempt_id, stage="video_cycle", state="BLOCKED", reason=type(exc).__name__)
        raise
    row["attemptId"] = attempt_id
    save_attempt(attempt_id, stage="pool_admission", state=row["state"],
                 sessionFile=row.get("sessionFile"), reason="CONSUMER_NOT_YET_PROVEN")
    return row


def _capture_and_graduate_video(account: dict[str, Any], job_wait: float, sso_budget: float,
                                attempt_id: str) -> dict[str, Any]:
    """One seat: exact-host SSO -> project -> capture -> Python render -> admission."""
    host, label = str(account["host"]), str(account["label"])
    path = _video_session_path(host, label)
    sso_command = [sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port",
                   str(account["port"]), "--drive", "--include-video", "--host-exact", host,
                   "--budget", str(sso_budget)]
    sso_rc = run_bounded_child(sso_command, timeout=max(30.0, sso_budget + 30.0),
                               env=attempt_environment(attempt_id))
    if sso_rc is None:
        return {"profile": account["profile"], "port": account["port"], "label": label,
                "provider": account["provider"], "host": host, "ssoRc": "PARENT_TIMEOUT",
                "state": "NOT_ADMITTED", "detail": "parent deadline stopped a wedged video SSO child"}
    if sso_rc:
        return {"profile": account["profile"], "port": account["port"], "label": label,
                "provider": account["provider"], "host": host, "ssoRc": sso_rc,
                "state": "NOT_ADMITTED", "detail": "bounded video SSO recovery failed; capture not attempted"}
    started = time.time()
    save_attempt(attempt_id, stage="capture", state="RUNNING")
    cmd = [sys.executable, str(HERE / "capture_video_job_cdp.py"), "--port", str(account["port"]),
           "--match", str(account["url"]), "--url", str(account["url"]), "--host", host,
           "--seat", label, "--job-wait", str(job_wait)]
    rc = run_bounded_child(cmd, timeout=max(60.0, job_wait + 90.0), env=attempt_environment(attempt_id))
    row: dict[str, Any] = {"profile": account["profile"], "port": account["port"], "label": label,
                           "provider": account["provider"], "host": host, "ssoRc": sso_rc, "captureRc": rc,
                           "state": "NOT_ADMITTED"}
    if rc is None:
        row["captureRc"] = "PARENT_TIMEOUT"
        row["detail"] = "parent deadline stopped a wedged video capture child"
        return row
    if rc != 0 or not path.is_file() or path.stat().st_mtime < started - 2:
        row["detail"] = "video capture left no fresh correlated session artifact"
        return row
    try:
        save_attempt(attempt_id, stage="replay", state="RUNNING")
        row.update(verify_video_and_admit(path, attempt_id))
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
            else:
                try:
                    row["mediaProof"] = verify_media_delivery(url)
                    row["attributionVerified"] = body.get("provider") == host and bool(body.get("session"))
                    if not row["attributionVerified"]:
                        row["state"] = "CONSUMER_ATTRIBUTION_NOT_PROVEN"
                except Exception as exc:
                    row.update(state="CONSUMER_MEDIA_NOT_PROVEN", reason=type(exc).__name__)
            return row
        if state in {"failed", "cancelled", "canceled"}:
            row.update(state="CONSUMER_FAILED", pollHttp=status, detail=str(body.get("error") or state)[:180])
            return row
        time.sleep(5)
    row["state"] = "CONSUMER_TIMEOUT"
    return row


def consumer_chat_probe(host: str, session_file: str | None = None) -> dict[str, Any]:
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
    actual_session = str(body.get("session") or "")
    attributed = body.get("provider") == host and bool(actual_session)
    if session_file is not None:
        attributed = attributed and actual_session == pathlib.Path(session_file).stem
    return {"host": host, "model": f"{host}/auto", "http": status,
            "sessionFile": session_file, "actualProvider": body.get("provider"), "actualSession": actual_session,
            "state": "CONSUMER_E2E_PROVEN" if status == 200 and content.strip() == VERIFY_EXPECT and attributed
            else "CONSUMER_NOT_PROVEN", "computedAnswerObserved": content.strip() == VERIFY_EXPECT,
            "attributionVerified": attributed}


def e2e_chat_consumer_proofs() -> None:
    """Append one pinned consumer proof per admitted chat host to the durable run."""
    run = read_json(E2E_RUN, {})
    if not isinstance(run, dict):
        run = {}
    registry = load_registry()
    attempted_files = {str(item.get("sessionFile") or "") for profile in run.get("profiles", [])
                       for item in profile.get("captures", []) if isinstance(item, dict)
                       and item.get("state") == "ADMITTED_TO_8190_PURE_PYTHON"}
    run["consumerProofs"] = []
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict) or entry.get("state") != "ADMITTED" or entry.get("modality") != "chat":
            continue
        host, name = str(entry.get("host") or ""), str(entry.get("sessionFile") or "")
        if not host or not name or name not in attempted_files:
            continue
        raw = read_json(SECRETS / name, {})
        attempt_id = raw.get("graduation", {}).get("attemptId")
        try:
            proof = consumer_chat_probe(host, name)
        except Exception as exc:
            proof = {"host": host, "sessionFile": name, "state": "CONSUMER_TRANSPORT_FAILED",
                     "reason": type(exc).__name__}
        proof["attemptId"] = attempt_id
        if attempt_id:
            save_attempt(attempt_id, stage="consumer", state=proof["state"], consumerProof=proof)
        run["consumerProofs"].append(proof)
        atomic_json(E2E_RUN, run)
    atomic_json(E2E_RUN, run)


def e2e_video_apply(job_wait: float, sso_budget: float, selected_labels: set[str] | None = None) -> None:
    """Serial resumable video lane.

    With no selection, terminal seats are never automatically re-spent.  An
    explicit label selection is an operator-scoped retry request for exactly
    those labels; it is intentionally required by the CLI so a bounded proof
    authorization cannot widen into a fleet-wide spend.
    """
    prior = read_json(E2E_VIDEO_RUN, {})
    prior_seats = prior.get("seats") if isinstance(prior, dict) else []
    prior_proofs = prior.get("consumerProofs") if isinstance(prior, dict) else []
    seats = [dict(row) for row in prior_seats if isinstance(row, dict)] if isinstance(prior_seats, list) else []
    proofs = [dict(row) for row in prior_proofs if isinstance(row, dict)] if isinstance(prior_proofs, list) else []
    completed_labels = {str(row.get("label") or "") for row in seats if row.get("label") and row.get("state")}
    run = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "mode": "serial_all_profile_video_capture_python_graduation_consumer_proof",
           "consumerContract": "http://127.0.0.1:8190/v1", "seats": seats, "consumerProofs": proofs}
    if seats:
        run["resumedFrom"] = str(prior.get("generatedAt") or "unknown")
    selected = {str(label).strip() for label in (selected_labels or set()) if str(label).strip()}
    declared = declared_video_accounts()
    known_labels = {str(account["label"]) for account in declared}
    unknown = selected - known_labels
    if unknown:
        raise SystemExit(f"unknown --video-label(s): {', '.join(sorted(unknown))}")
    accounts = [account for account in declared if not selected or str(account["label"]) in selected]
    for account in accounts:
        label = str(account["label"])
        if not selected and label in completed_labels:
            print(f"video resume: {label} already has terminal evidence; not re-running", flush=True)
            continue
        row = capture_and_graduate_video(account, job_wait, sso_budget)
        run["seats"].append(row)
        atomic_json(E2E_VIDEO_RUN, run)
        time.sleep(4)
    # A pin selects a provider host, not an account label.  Prove every host
    # with at least one exact-file graduation, while the seat rows remain the
    # capacity source of truth.
    attempted_hosts = {str(row.get("host") or "") for row in run["consumerProofs"] if row.get("host")}
    for host in sorted({str(r["host"]) for r in run["seats"]
                        if r.get("state") == "ADMITTED_TO_8190_PURE_PYTHON" and str(r.get("host") or "")
                        not in attempted_hosts}):
        try:
            proof = consumer_video_probe(host)
        except Exception as exc:
            proof = {"host": host, "state": "CONSUMER_TRANSPORT_FAILED", "reason": type(exc).__name__}
        run["consumerProofs"].append(proof)
        atomic_json(E2E_VIDEO_RUN, run)
    print(f"all-profile video E2E complete: {E2E_VIDEO_RUN.name}")


def e2e_apply(sso_budget: float, capture_wait: float, limit: int, video_job_wait: float,
              selected_labels: set[str] | None = None) -> None:
    """The literal complete master sequence requested by the operator."""
    # Child video clients use this established explicit spend gate.  It is set
    # only inside the command that also required --confirm-video-spend.
    prior = os.environ.get("OMNI_VIDEO_CONFIRM_SPEND")
    os.environ["OMNI_VIDEO_CONFIRM_SPEND"] = "1"
    try:
        e2e_chat_apply(sso_budget, capture_wait, limit)
        e2e_chat_consumer_proofs()
        e2e_video_apply(video_job_wait, sso_budget, selected_labels)
    finally:
        if prior is None:
            os.environ.pop("OMNI_VIDEO_CONFIRM_SPEND", None)
        else:
            os.environ["OMNI_VIDEO_CONFIRM_SPEND"] = prior


def e2e_video_only_apply(job_wait: float, sso_budget: float, selected_labels: set[str] | None = None) -> None:
    """Run every declared video seat without repeating a completed chat lane."""
    prior = os.environ.get("OMNI_VIDEO_CONFIRM_SPEND")
    os.environ["OMNI_VIDEO_CONFIRM_SPEND"] = "1"
    try:
        e2e_video_apply(job_wait, sso_budget, selected_labels)
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
        plan_path = STATE / f"fleet_blueprint_plan_{port}.json"
        plan_path.unlink(missing_ok=True)
        rc = run_bounded_child([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port)],
                               timeout=max(120, sso_budget + 30))
        plan = read_json(plan_path, {})
        if rc != 0 or not isinstance(plan, dict) or not isinstance(plan.get("hosts"), list):
            unit.update(state="BLOCKED", failedStage="login", reason="FRESH_PLAN_NOT_PROVEN")
            run["profiles"].append(unit); atomic_json(E2E_RUN, run)
            continue
        attempts: dict[str, str] = {}
        failed_hosts: set[str] = set()
        for row in plan.get("hosts", []) if isinstance(plan, dict) else []:
            if not isinstance(row, dict):
                continue
            host = str(row.get("host") or "")
            if host:
                attempts[host] = uuid.uuid4().hex
                save_attempt(attempts[host], stage="login", state="OBSERVED", host=host,
                             profile=profile, port=port)
            if row.get("host") and row.get("signedOut") is not False:
                sso_report = STATE / f"fleet_blueprint_report_{port}.json"
                sso_report.unlink(missing_ok=True)
                rc = run_bounded_child([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port),
                                        "--drive", "--host-exact", host, "--budget", str(sso_budget)],
                                       timeout=max(30, sso_budget + 30), env=attempt_environment(attempts[host]))
                unit["sso"].append({"host": host, "rc": rc,
                                    "attemptId": attempts[host], "probe": str(row.get("signedOut"))})
                report = read_json(sso_report, {})
                results = report.get("results", []) if isinstance(report, dict) else []
                outcomes = [r for r in results if isinstance(r, dict) and r.get("host") == host]
                ready = (isinstance(report, dict) and report.get("attemptId") == attempts[host] and len(outcomes) == 1
                         and outcomes[0].get("state") == "EXISTING_ACCOUNT"
                         and not str(outcomes[0].get("detail", "")).startswith("skipped by knowledge table"))
                if rc != 0 or not ready:
                    failed_hosts.add(host)
                    unit["sso"][-1]["state"] = "BLOCKED"
                    save_attempt(attempts[host], stage="login", state="BLOCKED", reason="AUTH_READINESS_NOT_PROVEN")
                else:
                    save_attempt(attempts[host], stage="login", state="SURFACE_READY_IDENTITY_NOT_VERIFIED")
        # The harness is the navigation + bounded-SSO layer for tabs that are
        # authenticated but not yet sitting on a capture surface.  Its default
        # post-apply readiness audit is load-bearing: without it a just-signed-
        # in site remains stale SKIP_NOT_AUTHENTICATED in the next manifest.
        harness_rc = run_bounded_child([sys.executable, str(HERE / "harness_all_tabs.py"), "--port", str(port),
                                     "--apply", "--wait", "10", "--budget", str(max(120, int(sso_budget)))],
                                      timeout=max(180, sso_budget + 90))
        unit["harnessRc"] = harness_rc
        if harness_rc != 0:
            unit.update(state="BLOCKED", failedStage="login", reason="READINESS_CHILD_FAILED_OR_TIMED_OUT")
            run["profiles"].append(unit); atomic_json(E2E_RUN, run)
            continue
        manifest_path = STATE / f"fleet_e2e_manifest_{port}.json"
        manifest_path.unlink(missing_ok=True)
        rc = run_bounded_child([sys.executable, str(HERE / "tab_graduation_sweep.py"), "--port", str(port),
                               "--json", str(manifest_path)], timeout=180)
        manifest = read_json(manifest_path, {})
        if rc != 0 or not isinstance(manifest, dict) or not isinstance(manifest.get("tabs"), list):
            unit.update(state="BLOCKED", failedStage="capture", reason="FRESH_MANIFEST_NOT_PROVEN")
            run["profiles"].append(unit); atomic_json(E2E_RUN, run)
            continue
        seen: set[str] = set()
        for tab in manifest.get("tabs", []) if isinstance(manifest, dict) else []:
            if left <= 0 or tab.get("classification") != "ELIGIBLE_CAPTURE":
                continue
            site = str(tab.get("knownSite") or "")
            if not site or site in seen:
                continue
            host = str(tab.get("host") or urllib.parse.urlparse(str(tab.get("url") or tab.get("tabUrl") or "")).hostname or "")
            if host in failed_hosts:
                continue
            attempt_id = attempts.pop(host, None) or uuid.uuid4().hex
            seen.add(site); started = time.time()
            proof_path = scratch_report(site)
            proof_path.unlink(missing_ok=True)
            save_attempt(attempt_id, stage="capture", state="RUNNING", site=site, host=host,
                         profile=profile, port=port)
            rc = run_bounded_child([sys.executable, str(HERE / "tab_graduation_sweep.py"), "--port", str(port),
                                   "--execute", "--site", site, "--wait", str(capture_wait)],
                                  timeout=max(240, capture_wait + 180), env=attempt_environment(attempt_id))
            expected = SECRETS / f"session_{session_slug(site)}.json"
            item = {"site": site, "attemptId": attempt_id, "captureRc": rc, "state": "NOT_ADMITTED"}
            fresh_capture = rc == 0 and expected.exists() and expected.stat().st_mtime >= started - 2
            if fresh_capture:
                try:
                    item.update(state="ADMITTED_TO_8190_PURE_PYTHON", sessionFile=expected.name,
                                adapter=_admit_from_existing_proof(expected, proof_path, attempt_id))
                except Exception as exc:
                    item["detail"] = f"{type(exc).__name__}: {exc}"[:220]
            else:
                item["detail"] = "capture did not leave a fresh exact session artifact"
            save_attempt(attempt_id, stage="pool_admission" if item["state"] == "ADMITTED_TO_8190_PURE_PYTHON" else ("replay" if fresh_capture else "capture"),
                         state=item["state"], sessionFile=expected.name,
                         reason=item.get("detail", "CONSUMER_NOT_YET_PROVEN"))
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
    try:
        rc = subprocess.run(cmd, cwd=ROOT, check=False, timeout=max(30, budget + 30),
                            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}).returncode
    except subprocess.TimeoutExpired as exc:
        raise SystemExit("SSO recovery timed out; no capture or promotion performed") from exc
    if rc:
        raise SystemExit(f"SSO recovery unit failed with exit code {rc}; no capture or promotion performed")
    print("SSO recovery completed as surface evidence only. Run a separate guarded capture unit after reviewing its report.")


def _main() -> int:
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
    group.add_argument("--e2e-video", action="store_true",
                       help="all-profile video-only continuation; reuses chat evidence and does not re-drive chat seats")
    group.add_argument("--e2e", action="store_true",
                       help="COMPLETE all-profile master: SSO, chat capture/proof/admission, video capture/Python render/admission, and pinned :8190 video proof")
    ap.add_argument("--port", type=int, default=9222, help="dedicated automation CDP port for capture or SSO recovery")
    ap.add_argument("--sso-budget", type=float, default=240.0,
                    help="wall-clock seconds for one --recover-sso host")
    ap.add_argument("--capture-wait", type=float, default=25.0, help="per-seat capture wait in --e2e-chat")
    ap.add_argument("--limit", type=int, default=0, help="cap chat seats in --e2e-chat (0 = all)")
    ap.add_argument("--video-job-wait", type=float, default=420.0,
                    help="seconds to record one browser video job's submit -> poll -> result sequence")
    ap.add_argument("--video-label", action="append", default=[],
                    help="explicitly retry only this declared video label (repeatable; overrides terminal-seat skip)")
    ap.add_argument("--confirm-video-spend", action="store_true",
                    help="required with --apply --e2e; acknowledges real video renders in capture, Python proof, and pinned :8190 proof")
    args = ap.parse_args()
    if (args.verify_and_admit or args.capture_chat or args.recover_sso or args.e2e_chat or args.e2e_video or args.e2e) and not args.apply:
        ap.error("--apply is required: these operations send a provider request and/or change an admission")
    if args.video_label and not (args.e2e_video or args.e2e):
        ap.error("--video-label requires --e2e-video or --e2e")
    if (args.e2e or args.e2e_video) and not args.confirm_video_spend:
        ap.error("--apply --e2e/--e2e-video requires --confirm-video-spend because it deliberately renders real videos")
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
        e2e_chat_consumer_proofs()
    elif args.e2e_video:
        e2e_video_only_apply(args.video_job_wait, args.sso_budget, set(args.video_label))
    elif args.e2e:
        e2e_apply(args.sso_budget, args.capture_wait, args.limit, args.video_job_wait, set(args.video_label))
    ledger = inventory()
    atomic_json(LEDGER, ledger)
    summary = ledger["summary"]
    print(f"ledger: {LEDGER.name}; artifacts={summary['sessionArtifacts']}; "
          f"admittedChatFiles={summary['admittedChatFiles']}; "
          f"admittedVideoFiles={summary['admittedVideoFiles']}; "
          f"admittedSessionFiles={summary['admittedSessionFiles']}; states={summary['byState']}")
    if args.e2e_chat or args.e2e:
        run = read_json(E2E_RUN, {})
        profiles = run.get("profiles", [])
        proofs = run.get("consumerProofs", [])
        if (not proofs or any(p.get("state") == "BLOCKED" for p in profiles)
                or any(s.get("state") == "BLOCKED" for p in profiles for s in p.get("sso", []))
                or any(item.get("state") != "ADMITTED_TO_8190_PURE_PYTHON"
                       for p in profiles for item in p.get("captures", []))
                or any(proof.get("state") != "CONSUMER_E2E_PROVEN" for proof in proofs)):
            return 1
    if args.e2e_video or args.e2e:
        run = read_json(E2E_VIDEO_RUN, {})
        if (not run.get("consumerProofs")
                or any(row.get("state") != "ADMITTED_TO_8190_PURE_PYTHON" for row in run.get("seats", []))
                or any(row.get("state") != "CONSUMER_E2E_PROVEN" for row in run.get("consumerProofs", []))):
            return 1
    return 0


def main() -> int:
    if "--apply" in sys.argv[1:]:
        with controller_lock():
            return _main()
    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
