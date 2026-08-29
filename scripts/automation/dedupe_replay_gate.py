#!/usr/bin/env python3
"""One-shot repair: dedupe state/replay_check.json by host, IN PLACE, no requests.

The 2026-08-29T15:33Z gate carried 21 results rows for 19 hosts: chatgpt.com twice
(session_chatgpt_free_web.json + session_chatx.json, both REPLAY_OK) and veoaifree.com
twice (a WALL row and a REPLAY_OK row). results[] is consumed per host, so the
duplicates surfaced as phantom providers in :20130's /health. replay_check.py now
dedupes at write time; this script applies the SAME rule to the file already on disk
WITHOUT sending any request -- a full replay_check re-run would spend one live request
per session file, which is exactly what this repair must not do.

Rule (identical to replay_check.py): REPLAY_OK outranks everything; among equal
verdicts the first row wins. Atomic write (tmp + replace). Idempotent.
"""
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "state" / "replay_check.json"

RANK = {"REPLAY_OK": 0, "SINGLE_USE": 1, "RATE": 2, "AUTH": 3, "WALL": 4}


def dedupe(rows: list) -> list:
    best: dict = {}
    for row in rows:
        host = str(row.get("host") or "")
        prior = best.get(host)
        if prior is None or RANK.get(row.get("verdict"), 9) < RANK.get(prior.get("verdict"), 9):
            best[host] = row
    return list(best.values())


def main() -> int:
    data = json.loads(GATE.read_text(encoding="utf-8"))
    rows = data.get("results") or []
    new_rows = dedupe(rows)
    if len(new_rows) == len(rows):
        print(f"gate already deduped: {len(rows)} rows -- nothing to do")
        return 0
    data["results"] = new_rows
    data["dedupedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["dedupNote"] = ("one row per host; duplicate rows from multi-capture hosts "
                         "removed in place, no requests sent")
    ok = [r["host"] for r in new_rows if r.get("verdict") == "REPLAY_OK"]
    single = [r["host"] for r in new_rows if r.get("verdict") == "SINGLE_USE"]
    data["summary"] = {
        "replayable": sorted(set(ok)),
        "singleUseBound": sorted(set(single)),
        "other": sorted({r["host"] for r in new_rows
                         if r.get("verdict") not in ("REPLAY_OK", "SINGLE_USE")}),
    }
    temporary = GATE.with_suffix(GATE.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(GATE)
    print(f"gate deduped in place: {len(rows)} rows -> {len(new_rows)} rows "
          f"(no requests sent)")
    print(f"replayable hosts ({len(set(ok))}): {', '.join(sorted(set(ok)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
