#!/usr/bin/env python3
"""usage_tracker.py — real Codex token/quota usage from local session rollouts.

Codex writes every session to ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl.
Each `token_count` event carries:
  - total_token_usage: input/cached_input/output/reasoning/total tokens
  - rate_limits.primary.used_percent  <- THE EXACT METER the UI shows
  - rate_limits.primary.window_minutes + resets_at (epoch seconds)

Usage:
  python usage_tracker.py            # current meter + per-mission totals today
  python usage_tracker.py --watch    # refresh every 60s
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

SESSIONS = Path.home() / ".codex" / "sessions"

# mission -> rollout file mapping is by cwd recorded in session_meta
MISSION_HINTS = {
    "omniroute-monetizer": "monetizer",
    "neon_unified": "neon",
    "crypto-trader": "crypto",
    "ases_v3_1": "ases",
    "ideation": "ideation",
    "emergentsh": "emergentsh",
    "oioi": "oioi",
    "voice_agent_avatar": "avatar",
    "voice-agent-clinic": "avatar",
    "antigravity-kandover": "godshand",
}


def today_dir(offset_days: int = 0) -> Path:
    d = dt.date.today() + dt.timedelta(days=offset_days)
    return SESSIONS / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"


def parse_rollout(path: Path) -> dict:
    meta = {"file": path.name, "cwd": None, "model": None, "started": None}
    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
        "turns": 0,
    }
    last_rate = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = rec.get("type")
                if rtype == "session_meta":
                    p = rec.get("payload", {})
                    meta["cwd"] = p.get("cwd") or rec.get("cwd")
                    meta["started"] = p.get("timestamp") or rec.get("timestamp")
                elif rtype == "turn_context":
                    meta["model"] = rec.get("payload", {}).get("model")
                elif rtype == "event_msg":
                    payload = rec.get("payload", {})
                    if payload.get("type") == "token_count":
                        info = payload.get("info", {})
                        tot = info.get("total_token_usage", {})
                        for k in totals:
                            if k != "turns":
                                totals[k] = max(totals[k], tot.get(k, 0))
                        totals["turns"] += 1
                        rl = payload.get("rate_limits")
                        if rl:
                            last_rate = rl
    except OSError:
        pass
    return {"meta": meta, "totals": totals, "rate_limits": last_rate}


def mission_for(cwd: str | None) -> str:
    if not cwd:
        return "unknown"
    low = cwd.lower().replace("\\", "/")
    for hint, name in MISSION_HINTS.items():
        if hint.lower() in low:
            return name
    return Path(cwd).name


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def collect() -> dict:
    """Gather meter + per-mission totals from rollouts touched in the last 6 h."""
    rollouts = []
    for offset in (0, -1):  # today + yesterday (sessions can span midnight)
        d = today_dir(offset)
        if d.is_dir():
            rollouts.extend(sorted(d.glob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime))

    cutoff = time.time() - 6 * 3600
    live = [p for p in rollouts if p.stat().st_mtime >= cutoff]

    meter = None
    resets_at = None
    window_min = None
    per_mission: dict[str, dict] = {}
    grand = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
             "reasoning_output_tokens": 0, "total_tokens": 0, "turns": 0}

    for path in live:
        data = parse_rollout(path)
        m = mission_for(data["meta"]["cwd"])
        slot = per_mission.setdefault(m, {"input_tokens": 0, "cached_input_tokens": 0,
                                          "output_tokens": 0, "reasoning_output_tokens": 0,
                                          "total_tokens": 0, "turns": 0, "sessions": 0})
        for k in grand:
            slot[k] = slot.get(k, 0) + data["totals"][k]
            grand[k] += data["totals"][k]
        slot["sessions"] += 1
        rl = data["rate_limits"]
        if rl and rl.get("primary"):
            used = rl["primary"].get("used_percent")
            if used is not None:
                meter = used
                resets_at = rl["primary"].get("resets_at")
                window_min = rl["primary"].get("window_minutes")

    return {"meter": meter, "resets_at": resets_at, "window_min": window_min,
            "per_mission": per_mission, "grand": grand}


def render() -> None:
    now = dt.datetime.now()
    print("=" * 72)
    print(f"  CODEX USAGE TRACKER — {now:%Y-%m-%d %H:%M:%S}")
    print("=" * 72)

    data = collect()
    meter = data["meter"]
    resets_at = data["resets_at"]
    window_min = data["window_min"]
    per_mission = data["per_mission"]
    grand = data["grand"]

    if not per_mission:
        print("  No rollout files found.")
        return

    # ---- meter ----
    if meter is not None:
        remaining = 100.0 - meter
        bar_len = 40
        filled = int(round(meter / 100 * bar_len))
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\n  WEEKLY METER (from Codex rate_limits, exact):")
        print(f"  [{bar}] {meter:.1f}% used  |  {remaining:.1f}% REMAINS")
        if resets_at:
            reset_dt = dt.datetime.fromtimestamp(resets_at)
            delta = reset_dt - now
            hrs = delta.total_seconds() / 3600
            print(f"  Window: {window_min} min ({window_min/1440:.1f} days) | resets {reset_dt:%a %H:%M} (in {hrs:.1f} h)")
    else:
        print("\n  No rate-limit data captured yet this session.")

    # ---- per mission ----
    print(f"\n  PER-MISSION TOKENS (sessions touched in last 6 h):")
    print(f"  {'mission':<14} {'total':>9} {'fresh-in':>9} {'cached-in':>10} {'out':>8} {'reason':>8} {'turns':>6}")
    for m in sorted(per_mission, key=lambda x: -per_mission[x]["total_tokens"]):
        s = per_mission[m]
        fresh = s["input_tokens"] - s["cached_input_tokens"]
        print(f"  {m:<14} {fmt_tokens(s['total_tokens']):>9} {fmt_tokens(fresh):>9} "
              f"{fmt_tokens(s['cached_input_tokens']):>10} {fmt_tokens(s['output_tokens']):>8} "
              f"{fmt_tokens(s['reasoning_output_tokens']):>8} {s['turns']:>6}")
    fresh_grand = grand["input_tokens"] - grand["cached_input_tokens"]
    cache_pct = (grand["cached_input_tokens"] / grand["input_tokens"] * 100) if grand["input_tokens"] else 0
    print(f"  {'TOTAL':<14} {fmt_tokens(grand['total_tokens']):>9} {fmt_tokens(fresh_grand):>9} "
          f"{fmt_tokens(grand['cached_input_tokens']):>10} {fmt_tokens(grand['output_tokens']):>8} "
          f"{fmt_tokens(grand['reasoning_output_tokens']):>8} {grand['turns']:>6}")
    print(f"\n  Cache hit rate: {cache_pct:.0f}% of input tokens served from cache (billed at ~1/10).")
    print("=" * 72)


CSV_PATH = Path(__file__).resolve().parent.parent / "state" / "usage_history.csv"
CSV_HEADER = ("timestamp,meter_used_pct,turns_total,total_tokens,fresh_input_tokens,"
              "cached_input_tokens,output_tokens,reasoning_tokens,cache_hit_pct,"
              "monetizer_tokens,neon_tokens,crypto_tokens,ases_tokens,"
              "avatar_tokens,godshand_tokens\n")


def log_sample() -> None:
    """Append one CSV row of the current usage state (for overnight burn charts)."""
    data = collect()
    grand = data["grand"]
    meter = data["meter"]
    fresh = grand["input_tokens"] - grand["cached_input_tokens"]
    cache_pct = (grand["cached_input_tokens"] / grand["input_tokens"] * 100) if grand["input_tokens"] else 0.0
    pm = data["per_mission"]
    row = [
        dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"{meter:.1f}" if meter is not None else "",
        grand["turns"], grand["total_tokens"], fresh,
        grand["cached_input_tokens"], grand["output_tokens"],
        grand["reasoning_output_tokens"], f"{cache_pct:.1f}",
        pm.get("monetizer", {}).get("total_tokens", 0),
        pm.get("neon", {}).get("total_tokens", 0),
        pm.get("crypto", {}).get("total_tokens", 0),
        pm.get("ases", {}).get("total_tokens", 0),
        pm.get("avatar", {}).get("total_tokens", 0),
        pm.get("godshand", {}).get("total_tokens", 0),
    ]
    new_file = not CSV_PATH.exists()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "a", encoding="utf-8") as fh:
        if new_file:
            fh.write(CSV_HEADER)
        fh.write(",".join(str(v) for v in row) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="refresh every 60 s (foreground)")
    ap.add_argument("--log", action="store_true",
                    help="poll every 60 s, print live AND append history to state/usage_history.csv")
    ap.add_argument("--sample", action="store_true",
                    help="one-shot: append CSV row and print a machine-parseable SAMPLE line")
    ap.add_argument("--interval", type=int, default=60, help="poll interval seconds (default 60)")
    args = ap.parse_args()
    if args.sample:
        log_sample()
        data = collect()
        g = data["grand"]
        pm = data["per_mission"]
        meter = data["meter"]
        print("SAMPLE meter=" + (f"{meter:.1f}" if meter is not None else "NA")
              + f" turns={g['turns']} total={g['total_tokens']}"
              + f" monetizer={pm.get('monetizer', {}).get('total_tokens', 0)}"
              + f" neon={pm.get('neon', {}).get('total_tokens', 0)}"
              + f" crypto={pm.get('crypto', {}).get('total_tokens', 0)}"
              + f" ases={pm.get('ases', {}).get('total_tokens', 0)}"
              + f" avatar={pm.get('avatar', {}).get('total_tokens', 0)}"
              + f" godshand={pm.get('godshand', {}).get('total_tokens', 0)}")
        return
    if not (args.watch or args.log):
        render()
        return
    try:
        while True:
            render()
            if args.log:
                log_sample()
                print(f"\n  (logged to {CSV_PATH.name}; next poll in {args.interval} s — Ctrl+C to stop)\n")
            else:
                print(f"\n  (auto-refresh in {args.interval} s — Ctrl+C to stop)\n")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
