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

Video is represented in the ledger but is never auto-triggered: a video proof
can spend credits and must use its separate submit -> poll -> result contract.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
from collections import Counter
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "state"
SECRETS = STATE / "secrets"
LEDGER = STATE / "fleet_graduation_ledger.json"
E2E_PLAN = STATE / "fleet_e2e_graduation_plan.json"
E2E_RUN = STATE / "fleet_e2e_graduation_run.json"
SEAT_ACCOUNTS = STATE / "video_accounts.json"
SCRATCH = STATE / "scratch"
VERIFY_PROMPT = "Reply with only the number: 41 + 17"
VERIFY_EXPECT = "58"

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
            "run video submit-poll-result graduation separately with explicit spend confirmation",
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
        elif modality == "video":
            state = "VIDEO_PROOF_REQUIRED"
            next_action = "record submit-poll-result then explicit spend-gated adapter proof"
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
        # Plan gives current dedicated-seat hosts; only signed-out rows are driven.
        subprocess.run([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port)], cwd=ROOT, check=False)
        plan = read_json(STATE / f"fleet_blueprint_plan_{port}.json", {})
        for row in plan.get("hosts", []) if isinstance(plan, dict) else []:
            if row.get("signedOut") is True and row.get("host"):
                host = str(row["host"])
                rc = subprocess.run([sys.executable, str(HERE / "fleet_sso_blueprint.py"), "--port", str(port),
                                     "--drive", "--host-exact", host, "--budget", str(sso_budget)], cwd=ROOT, check=False).returncode
                unit["sso"].append({"host": host, "rc": rc})
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
    ap.add_argument("--port", type=int, default=9222, help="dedicated automation CDP port for capture or SSO recovery")
    ap.add_argument("--sso-budget", type=float, default=240.0,
                    help="wall-clock seconds for one --recover-sso host")
    ap.add_argument("--capture-wait", type=float, default=25.0, help="per-seat capture wait in --e2e-chat")
    ap.add_argument("--limit", type=int, default=0, help="cap chat seats in --e2e-chat (0 = all)")
    args = ap.parse_args()
    if (args.verify_and_admit or args.capture_chat or args.recover_sso or args.e2e_chat) and not args.apply:
        ap.error("--apply is required: these operations send a provider request and/or change an admission")
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
    ledger = inventory()
    atomic_json(LEDGER, ledger)
    summary = ledger["summary"]
    print(f"ledger: {LEDGER.name}; artifacts={summary['sessionArtifacts']}; "
          f"admittedChatFiles={summary['admittedChatFiles']}; states={summary['byState']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
