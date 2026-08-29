#!/usr/bin/env python3
"""Backfill a graduation run's ledger/worklog records from its transcript. No request is sent.

Run 3 (2026-08-29 evening) completed all 31 planned seats, rebuilt the canonical gate and
restarted :20130 -- then the orchestrator died (defect D1, since fixed) before ledger['runs']
and the worklog were written. Run 4 died the same way for a different reason: the agent
console's stdout transcoder stopped draining, so the orchestrator's next print() blocked
forever and the console later killed the process hard -- while the per-seat ledger writes
had again preserved every verdict. The complete transcript survives in each run's log;
this script replays THAT FILE into the two missing sinks:

  * state/graduation_ledger.json -> runs[] gains the run record, with the verdict
    table inline (the same shape future runs write, including 'rows');
  * MASTER_WORKLOG.md            -> a numbered entry (#N = active stream + 1) carrying
    the per-seat verdict table.

The ledger's per-seat entries are already current (save_ledger runs after every seat); only
the two end-of-run sinks are ever lost. Idempotent PER LOG: a 'sourceLog' marker in runs[]
makes re-runs for the same transcript exit without touching anything. When the step-3 line
is missing from the transcript (the run died before it), the graduated list is derived from
the parsed rows' REPLAY_OK verdicts and the record says so.

Usage:
    python scripts/automation/backfill_run3_records.py \
        [--log state/grad_apply_run4.log --label "run 4"]
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from graduate_all_seats import LEDGER, WORKLOG, next_worklog_number  # noqa: E402


def _read_text(path: pathlib.Path) -> str:
    """Transcript encoding is whatever launched the run: a PowerShell '*>' redirect writes
    UTF-16LE, a shell '>' or python-side redirect writes UTF-8. Decode by BOM, then guess."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-16", errors="replace")

LOG = ROOT / "state" / "grad_apply_run3.log"   # default; --log overrides


def parse_log(text: str):
    rows, skips, graduated, meta = [], [], [], {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^tabs (\d+)\s+eligible sites (\d+)\s+planned (\d+)\s+"
                     r"skipped (\d+)\s+video lane (\d+)", line)
        if m:
            meta = dict(zip(("tabs", "eligible", "planned", "skipped", "video"),
                            (int(m.group(i)) for i in range(1, 6))))
            continue
        m = re.match(r"^  skip  (.+?)\s{2,}(.+)$", line)
        if m:
            skips.append((m.group(1).strip(), m.group(2).strip()))
            continue
        m = re.match(r"^\[(\d+)/(\d+)\] (.+) \(([^()]*)\)$", line)
        if m:
            # Host = the LAST parenthesised group (site names themselves contain
            # parentheses: 'Qwen Chat (Alibaba)  (chat.qwen.ai)' must split into
            # site='Qwen Chat (Alibaba)', host='chat.qwen.ai').
            current = {"site": m.group(3).strip(), "host": m.group(4).strip()}
            continue
        m = re.match(r"^\s+steps 1-2\s+([A-Z_]+)\s*(.*)$", line)
        if m and current:
            current["verdict"] = m.group(1).strip()
            current["detail"] = m.group(2).strip()
            rows.append(current)
            current = None
            continue
        m = re.match(r"^step 3 graduate -- (\d+) seat\(s\) replayed clean: (.*)$", line)
        if m:
            graduated = [s.strip() for s in m.group(2).split(",") if s.strip()]
    return rows, skips, graduated, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--log", default="state/grad_apply_run3.log",
                    help="run transcript to backfill from, relative to the repo root")
    ap.add_argument("--label", default="",
                    help="run label for the worklog title (e.g. 'run 4')")
    a = ap.parse_args()

    log_path = (ROOT / a.log).resolve()
    if not log_path.exists():
        print(f"transcript missing: {log_path}")
        return 1
    rows, skips, graduated, meta = parse_log(_read_text(log_path))
    at = int(os.path.getmtime(log_path))
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(at))
    planned = meta.get("planned", len(rows))
    step3_reached = bool(graduated)
    if not graduated:
        # A transcript that ends before step 3 still tells us who graduated: the rows do.
        graduated = [r["site"] for r in rows if r.get("verdict") == "REPLAY_OK"]

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    runs = ledger.get("runs", [])
    if any(r.get("sourceLog") == log_path.name for r in runs):
        print(f"{log_path.name} already backfilled into ledger runs[] -- nothing to do")
        return 0

    table = [f"| {r['site']} | {r['host']} | {r['verdict']} | "
             f"{r['detail'][:70].replace('|', '/')} | "
             f"{'yes' if r['verdict'] == 'REPLAY_OK' else 'no'} |"
             for r in rows]

    ledger.setdefault("runs", []).append({
        "at": at,
        "planned": planned,
        "graduated": graduated,
        "rows": table,
        "sourceLog": log_path.name,
        "backfilled": ("2026-08-29: the orchestrator died before its end-of-run writes; "
                       "reconstructed from " + log_path.name + " by "
                       "scripts/automation/backfill_run3_records.py -- no request re-sent"
                       + ("" if step3_reached else
                          "; step 3 (gate regen/restart) never ran, graduated list derived "
                          "from the rows' REPLAY_OK verdicts")),
    })
    temporary = LEDGER.with_suffix(LEDGER.suffix + ".tmp")
    temporary.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    temporary.replace(LEDGER)
    print(f"ledger: runs[] now {len(ledger['runs'])} entries "
          f"({a.label or log_path.name} backfilled)")

    n = next_worklog_number()
    body = [
        f"\n### [{stamp}] #{n} — graduate_all_seats {a.label or 'run'} (BACKFILLED): "
        f"{len(graduated)}/{planned} graduated\n",
        f"**Backfill note:** transcript `{log_path.name}` parsed; no request was re-sent. "
        f"The ledger's per-seat entries were already current (save_ledger ran per seat) -- "
        f"only the end-of-run sinks were lost."
        + ("" if step3_reached else
           " **The transcript ends before step 3:** the orchestrator died (run 4: the agent "
           "console's stdout transcoder stopped draining, so the next print() blocked "
           "forever, and the console later killed the process) after the per-seat writes; "
           "the graduated list is derived from the rows' REPLAY_OK verdicts, and the gate "
           "regen / pool restart never ran."),
        f"Graduated: {', '.join(graduated) or '-'}",
        f"Skipped before start ({len(skips)}): "
        + "; ".join(f"{s} — {why}" for s, why in skips),
        "",
        "| seat | host | verdict | detail | graduated |",
        "|---|---|---|---|---|",
    ] + table + [""]
    with WORKLOG.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")
    print(f"worklog: entry #{n} appended to {WORKLOG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
