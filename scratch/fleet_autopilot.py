#!/usr/bin/env python3
"""fleet_autopilot.py — polls the Codex usage meter every 60 s and applies the
agreed throttle rules automatically (kill-only; never resumes; never touches
monetizer).

Rules (REMAINING weekly meter):
  > 70%   : ALL_RUN  — no action
  60-70%  : CAUTION  — log only
  40-60%  : TRIM     — stop crypto + ases, keep monetizer + neon
  < 40%   : CRITICAL — stop neon too, keep monetizer only

Kills are one-shot per threshold episode (state in state/autopilot_state.json).
When the meter recovers to ALL_RUN, kill-guards reset so a later dip can
re-trim (manual restarts are respected until the next dip).
All actions logged to state/autopilot.log.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_tracker import collect  # noqa: E402

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
LOG = STATE_DIR / "autopilot.log"
STATE = STATE_DIR / "autopilot_state.json"
INTERVAL = 60

MISSIONS = {
    "monetizer": r"d:\omniroute-monetizer",
    "neon": r"d:\neon_unified",
    "crypto": r"C:\god_ai\crypto-trader-v1_1",
    "ases": r"C:\god_ai\ases_v3_1",
}
PROTECTED = {"monetizer"}          # never killed
TRIM_ORDER = ["crypto", "ases"]    # first to go at TRIM
CRITICAL_EXTRA = ["neon"]          # additionally goes at CRITICAL


def log(msg: str) -> None:
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"killed": {}, "level": None}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def codex_processes() -> list:
    """Return [{pid, cmdline}] for all codex.exe processes.

    Uses -EncodedCommand because passing embedded double quotes through
    subprocess -> powershell -Command is unreliable on Windows PowerShell 5.1
    (the escaped \" quotes can break parsing and yield empty output).
    """
    ps_cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    encoded = base64.b64encode(ps_cmd.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True, text=True, timeout=30,
        )
        out = r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return []
    if not out:
        return []
    try:
        # strict=False: CommandLine embeds the full mission prompt, which can
        # contain raw control characters that ConvertTo-Json does not escape.
        data = json.loads(out, strict=False)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [{"pid": d.get("ProcessId"), "cmdline": d.get("CommandLine") or ""} for d in data]


def mission_pid(mission: str):
    workdir = MISSIONS[mission].lower()
    procs = codex_processes()
    for p in procs:
        if workdir in p["cmdline"].lower():
            return p["pid"]
    return None


def kill_mission(mission: str) -> bool:
    """Kill a mission's codex process. Returns False (do NOT mark killed) if
    process detection itself failed, so we retry on the next poll instead of
    silently believing the mission is gone."""
    procs = codex_processes()
    if not procs:
        log(f"  {mission}: process detection returned nothing - retrying next poll (not marking killed)")
        return False
    workdir = MISSIONS[mission].lower()
    pid = None
    for p in procs:
        if workdir in p["cmdline"].lower():
            pid = p["pid"]
            break
    if pid is None:
        log(f"  {mission}: no live codex process found among {len(procs)} detected (already stopped)")
        return True
    r = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True)
    ok = r.returncode == 0
    detail = (r.stdout.strip() or r.stderr.strip()).replace("\r", " ").replace("\n", " ")
    log(f"  {mission}: {'KILLED' if ok else 'kill FAILED'} pid={pid} ({detail})")
    return ok


def level_for(remaining: float) -> str:
    if remaining > 70:
        return "ALL_RUN"
    if remaining > 60:
        return "CAUTION"
    if remaining > 40:
        return "TRIM"
    return "CRITICAL"


def main() -> None:
    log("AUTOPILOT STARTED (interval=60 s)")
    log("rules: >70 ALL_RUN | 60-70 CAUTION | 40-60 TRIM crypto+ases | <40 CRITICAL keep monetizer only")
    st = load_state()
    while True:
        try:
            data = collect()
            meter = data["meter"]
            if meter is None:
                log("poll: no meter data yet — skipping")
                time.sleep(INTERVAL)
                continue
            remaining = 100.0 - meter
            level = level_for(remaining)
            turns = data["grand"]["turns"]
            log(f"poll: meter {meter:.1f}% used / {remaining:.1f}% remains | turns={turns} | level={level}")

            # Recovery: reset kill-guards so future dips can trim again.
            if level == "ALL_RUN" and st["killed"]:
                log("meter recovered to ALL_RUN — kill-guards reset (manual restarts respected)")
                st["killed"] = {}
                save_state(st)

            targets = []
            if level in ("TRIM", "CRITICAL"):
                targets += TRIM_ORDER
            if level == "CRITICAL":
                targets += CRITICAL_EXTRA
            for m in targets:
                if m in PROTECTED or m in st["killed"]:
                    continue
                if kill_mission(m):
                    st["killed"][m] = dt.datetime.now().isoformat(timespec="seconds")
                    save_state(st)

            if level != st.get("level"):
                log(f"level change: {st.get('level')} -> {level}")
                st["level"] = level
                save_state(st)
        except Exception as exc:  # never die
            log(f"poll error: {exc!r}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("AUTOPILOT STOPPED (Ctrl+C)")
