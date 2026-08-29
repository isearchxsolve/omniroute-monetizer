#!/usr/bin/env python3
"""One-shot backfill of graduation run 3 (handover defect D3). No request is sent.

Run 3 (2026-08-29 evening) completed all 31 planned seats, rebuilt the canonical gate
(`{'REPLAY_OK': 11, 'NO_ANSWER': 6, 'AUTH': 2, 'WALL': 2}`) and restarted :20130 --
then the orchestrator died (defect D1, since fixed) before ledger['runs'] and the
worklog were written. The complete transcript survives at state/grad_apply_run3.log;
this script replays THAT FILE into the two missing sinks:

  * state/graduation_ledger.json -> runs[] gains the run-3 record, with the verdict
    table inline (the same shape future runs write, including 'rows');
  * MASTER_WORKLOG.md            -> a numbered entry (#N = active stream + 1) carrying
    the 31-seat verdict table.

The ledger's per-seat entries were already current (save_ledger ran after every seat);
only the two end-of-run sinks were lost. Idempotent: a 'backfilled' marker in runs[]
makes re-runs exit without touching anything.
"""
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

LOG = ROOT / "state" / "grad_apply_run3.log"


def parse_log():
    rows, skips, graduated, meta = [], [], [], {}
    current = None
    text = LOG.read_text(encoding="utf-8", errors="replace")
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
    if not LOG.exists():
        print(f"transcript missing: {LOG}")
        return 1
    rows, skips, graduated, meta = parse_log()
    at = int(os.path.getmtime(LOG))
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(at))

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    runs = ledger.get("runs", [])
    if any(r.get("backfilled") for r in runs):
        print("run-3 record already present in ledger -- nothing to do")
        return 0

    table = [f"| {r['site']} | {r['host']} | {r['verdict']} | "
             f"{r['detail'][:70].replace('|', '/')} | "
             f"{'yes' if r['verdict'] == 'REPLAY_OK' else 'no'} |"
             for r in rows]

    ledger.setdefault("runs", []).append({
        "at": at,
        "planned": meta.get("planned", len(rows)),
        "graduated": graduated,
        "rows": table,
        "backfilled": ("2026-08-29: run 3 died after the :20130 restart (defect D1, since "
                       "fixed in graduate_all_seats.py) before its ledger/worklog writes; "
                       "reconstructed from state/grad_apply_run3.log by "
                       "scripts/automation/backfill_run3_records.py -- no request re-sent"),
    })
    temporary = LEDGER.with_suffix(LEDGER.suffix + ".tmp")
    temporary.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    temporary.replace(LEDGER)
    print(f"ledger: runs[] now {len(ledger['runs'])} entries (run 3 backfilled)")

    n = next_worklog_number()
    planned = meta.get("planned", len(rows))
    body = [
        f"\n### [{stamp}] #{n} — graduate_all_seats run 3 (BACKFILLED): "
        f"{len(graduated)}/{planned} graduated\n",
        f"**Backfill note:** run 3 completed all {planned} planned seats and rebuilt the "
        f"canonical gate (`{{'REPLAY_OK': 11, 'NO_ANSWER': 6, 'AUTH': 2, 'WALL': 2}}`), then "
        f"died after the :20130 restart (defect D1, fixed this session) before its "
        f"ledger/worklog writes. Table reconstructed verbatim from `state/grad_apply_run3.log`; "
        f"no request was re-sent. Ledger per-seat entries were already current "
        f"(save_ledger ran per seat).",
        f"Graduated: {', '.join(graduated)}",
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
