"""Fleet monitor — one-command view of all 6 agents' live work.

Reads the per-slot logs written by aider (state/fleet_logs/) plus each
project's FLEET_WORKLOG.md (the agent-maintained summary feed) and prints
a compact status board: last activity time, log sizes, and the latest
worklog entry per agent.

Usage:  python fleet_monitor.py            # status board
        python fleet_monitor.py --tail 5   # last 5 lines of each chat log
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

FLEET_LOGS = Path(r"d:\omniroute-monetizer\state\fleet_logs")
CODEX_LOGS = Path(r"d:\omniroute-monetizer\state\codex_fleet_logs")

# slot -> project dir (where the agent writes FLEET_WORKLOG.md)
PROJECTS = {
    "nvidia-1": r"d:\ideation_to_prototype",
    "nvidia-2": r"d:\emergentsh_latest",
    "alibaba": r"d:\neon_unified",
    "tokenrouter-1": r"C:\god_ai\oioi\oioi",
    "tokenrouter-2": r"C:\god_ai\crypto-trader-v1_1",
    "tokenrouter-3": r"C:\god_ai\ases_v3_1",
}

# codex mission -> project dir (same projects, ChatGPT Plus agents)
CODEX_MISSIONS = {
    "codex-monetizer": r"d:\omniroute-monetizer",
    "codex-ideation": r"d:\ideation_to_prototype",
    "codex-emergentsh": r"d:\emergentsh_latest",
    "codex-neon": r"d:\neon_unified",
    "codex-oioi": r"C:\god_ai\oioi\oioi",
    "codex-crypto": r"C:\god_ai\crypto-trader-v1_1",
    "codex-ases": r"C:\god_ai\ases_v3_1",
}


def age(ts: float) -> str:
    d = datetime.now().timestamp() - ts
    if d < 60:
        return f"{int(d)}s ago"
    if d < 3600:
        return f"{int(d // 60)}m ago"
    return f"{int(d // 3600)}h{int((d % 3600) // 60)}m ago"


def last_llm_activity(slot: str):
    """Newest LLM call from the jsonl history (timestamp + model)."""
    p = FLEET_LOGS / f"{slot}_llm.jsonl"
    if not p.exists():
        return None
    last = None
    try:
        with p.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return last


def last_worklog_entry(project: str):
    """Last '### [step N]' entry from the agent's FLEET_WORKLOG.md."""
    p = Path(project) / "FLEET_WORKLOG.md"
    if not p.exists():
        return None, None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    entries = [l for l in text.splitlines() if l.startswith("### ")]
    return (entries[-1].strip() if entries else None), p.stat().st_mtime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=0,
                    help="also print the last N lines of each chat log")
    args = ap.parse_args()

    print("=" * 72)
    print("FLEET STATUS BOARD  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)
    for slot, project in PROJECTS.items():
        chat = FLEET_LOGS / f"{slot}_chat.md"
        llm = FLEET_LOGS / f"{slot}_llm.jsonl"
        chat_size = chat.stat().st_size if chat.exists() else 0
        chat_mtime = chat.stat().st_mtime if chat.exists() else None
        last = last_llm_activity(slot)
        entry, entry_mtime = last_worklog_entry(project)

        print(f"\n[{slot}]  project={project}")
        if chat_size:
            print(f"  chat log : {chat_size:>8} bytes, updated {age(chat_mtime)}")
        else:
            print("  chat log : (not started yet)")
        if last:
            ts = last.get("timestamp") or last.get("ts") or ""
            print(f"  last LLM : {ts}")
        if entry:
            print(f"  worklog  : {entry}  (updated {age(entry_mtime)})")
        else:
            print("  worklog  : (no FLEET_WORKLOG.md yet)")

        if args.tail and chat.exists():
            lines = chat.read_text(encoding="utf-8", errors="replace").splitlines()
            print("  --- tail ---")
            for l in lines[-args.tail:]:
                print(f"  {l}")

    # ---------------- Codex fleet (ChatGPT Plus) ----------------
    print()
    print("=" * 72)
    print("CODEX FLEET (ChatGPT Plus)  — events: state/codex_fleet_logs/")
    print("=" * 72)
    for mission, project in CODEX_MISSIONS.items():
        events = CODEX_LOGS / f"{mission.replace('codex-', '')}_events.jsonl"
        last = CODEX_LOGS / f"{mission.replace('codex-', '')}_last.md"
        entry, entry_mtime = last_worklog_entry(project)

        print(f"\n[{mission}]  project={project}")
        if events.exists() and events.stat().st_size:
            n_events, last_type = _codex_event_stats(events)
            print(f"  events   : {events.stat().st_size:>8} bytes, {n_events} events, "
                  f"updated {age(events.stat().st_mtime)}  (last: {last_type})")
        else:
            print("  events   : (not started yet)")
        if last.exists() and last.stat().st_size:
            print(f"  final msg: written ({last.stat().st_size} bytes) — task FINISHED")
        if entry:
            print(f"  worklog  : {entry}  (updated {age(entry_mtime)})")
        else:
            print("  worklog  : (no FLEET_WORKLOG.md yet)")
        if args.tail and events.exists():
            lines = events.read_text(encoding="utf-8", errors="replace").splitlines()
            print("  --- tail ---")
            for l in lines[-args.tail:]:
                print("  " + l[:200])
    print()


def _codex_event_stats(events: Path):
    """Count JSONL events and return (count, last event type)."""
    n, last_type = 0, "?"
    try:
        with events.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n += 1
                try:
                    last_type = json.loads(line).get("type", "?")
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return n, last_type


if __name__ == "__main__":
    sys.exit(main())
