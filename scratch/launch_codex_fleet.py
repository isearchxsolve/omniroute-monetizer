"""Codex fleet launcher — headless autonomous agents on ChatGPT Plus (no API keys).

Uses the Codex CLI's `codex exec` (non-interactive) mode with the ChatGPT
account auth already in ~/.codex/auth.json. Unlike the aider fleet, Codex
runs shell commands natively with approval_policy="never" — there is NO
confirmation gate, so agents can actually run tests, iterate, and verify.

Binary discovery: codex.exe lives in a VERSIONED hash dir that changes on
every app update, so we auto-discover the newest one under Codex\\bin.

Logs (per mission):
  state/codex_fleet_logs/<mission>_events.jsonl  -- full --json event stream
  state/codex_fleet_logs/<mission>_last.md       -- agent's final message
  <project>/FLEET_WORKLOG.md                     -- agent-maintained live feed

Usage:
  python launch_codex_fleet.py --list
  python launch_codex_fleet.py neon crypto --dry-run
  python launch_codex_fleet.py neon crypto
  python launch_codex_fleet.py neon --model gpt-5.6-sol --effort max
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CODEX_BIN_ROOT = Path(r"C:\Users\Admin\AppData\Local\OpenAI\Codex\bin")
WRAPPER = Path(__file__).parent / "aider_session_wrapper.py"  # generic keep-open runner
GOAL_DIR = Path(r"d:\omniroute-monetizer\state\fleet_goals")
CODEX_LOGS = Path(r"d:\omniroute-monetizer\state\codex_fleet_logs")
LAUNCH_SPECS = Path(r"d:\omniroute-monetizer\state\launch_specs")

# mission -> (project dir, goal file). ORDER = PRIORITY: monetizer is the
# bloodline (supplies the model forest every other project consumes) -> first.
# avatar = #1 revenue candidate (named customer: clinics) per 2026-08-17
# YouTube-transcript analysis (worklog #90-92).
MISSIONS = {
    "monetizer":  (r"d:\omniroute-monetizer",           "monetizer_master.md"),
    "avatar":     (r"D:\god_ai\voice_agent_avatar\voice-agent-clinic", "avatar_voice_agent_clinic.md"),
    "ideation":   (r"d:\ideation_to_prototype",        "nvidia-1_ideation_to_prototype.md"),
    # NOTE: emergentsh live copy is C:\god_ai\emergentsh (merged 2026-08-17, worklog #98).
    # d:\emergentsh_latest is a STALE copy with none of the merged files — do not use.
    "emergentsh": (r"C:\god_ai\emergentsh",             "nvidia-2_emergentsh_latest.md"),
    "neon":       (r"d:\neon_unified",                 "alibaba_neon_unified.md"),
    "oioi":       (r"C:\god_ai\oioi\oioi",             "tokenrouter-1_oioi.md"),
    "crypto":     (r"C:\god_ai\crypto-trader-v1_1",    "tokenrouter-2_crypto-trader.md"),
    "ases":       (r"C:\god_ai\ases_v3_1",             "tokenrouter-3_ases_v3_1.md"),
}

# Budget strategy (ChatGPT Plus rate card): terra = cheap always-on worker,
# sol = escalation for genuinely nasty problems. Default terra/high.
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_EFFORT = "high"


def find_codex():
    """Newest codex.exe under the versioned bin dirs (hash changes on update)."""
    candidates = sorted(CODEX_BIN_ROOT.glob("*/codex.exe"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit(f"ERROR: no codex.exe found under {CODEX_BIN_ROOT}")
    return candidates[0]


def build_cmd(codex, mission, workdir, goal, model, effort):
    events = CODEX_LOGS / f"{mission}_events.jsonl"
    last = CODEX_LOGS / f"{mission}_last.md"
    cmd = [
        str(codex), "exec",
        "-C", workdir,
        "-m", model,
        "-c", f"model_reasoning_effort={effort}",
        "-s", "danger-full-access",   # explicit: no sandbox/approval gates in automation
        "--json",                     # full event stream -> captured to events.jsonl
        "-o", str(last),              # final agent message
        goal,
    ]
    return cmd, events, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("missions", nargs="*", help="mission names to launch")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"model (default {DEFAULT_MODEL}; escalate to gpt-5.6-sol if stuck)")
    ap.add_argument("--effort", default=DEFAULT_EFFORT,
                    help=f"reasoning effort low|medium|high|max (default {DEFAULT_EFFORT})")
    args = ap.parse_args()

    if args.list or not args.missions:
        print("Codex missions (mission -> project):")
        for m, (d, g) in MISSIONS.items():
            print(f"  {m:11s} {d}   [{g}]")
        print(f"\nDefault model: {args.model} / effort {args.effort}")
        print("Launch:  python launch_codex_fleet.py neon crypto")
        print("NOTE: Plus quota is shared across all parallel agents — start with")
        print("      2-3 missions, watch the monitor, then add more.")
        return 0

    codex = find_codex()
    print(f"codex binary: {codex}")
    CODEX_LOGS.mkdir(parents=True, exist_ok=True)
    LAUNCH_SPECS.mkdir(parents=True, exist_ok=True)

    for mission in args.missions:
        if mission not in MISSIONS:
            print(f"unknown mission: {mission} (use --list)")
            continue
        workdir, goal_file = MISSIONS[mission]
        goal = (GOAL_DIR / goal_file).read_text(encoding="utf-8").strip()
        cmd, events, last = build_cmd(codex, mission, workdir, goal,
                                      args.model, args.effort)
        if args.dry_run:
            print(f"\n[{mission}] {workdir}")
            print("  " + " ".join(cmd[:10]) + f" ... <goal {len(goal)} chars>")
            continue
        spec_path = LAUNCH_SPECS / f"codex_{mission}.json"
        spec_path.write_text(json.dumps({
            "slot": f"codex-{mission}",
            "cmd": cmd,
            "cwd": workdir,
            "stdout_log": str(events),   # wrapper redirects --json stream here
        }, indent=2), encoding="utf-8")
        env = dict(os.environ)
        subprocess.Popen(
            [sys.executable, str(WRAPPER), str(spec_path)],
            env=env, cwd=workdir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print(f"[{mission}] spawned -> {workdir}  (events: {events.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
