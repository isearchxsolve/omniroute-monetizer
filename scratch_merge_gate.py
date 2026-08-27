"""Merge all replay_check backups into one complete gate file.
Keeps the best verdict per host (REPLAY_OK > others), most recent row wins on ties.
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / "state"

RANK = {"REPLAY_OK": 0}  # only REPLAY_OK matters for the gate; everything else is equal

sources = [
    STATE / "replay_check.bak_20260827.json",   # original pre-capture
    STATE / "replay_check.bak2_20260827.json",  # after first 12 replay checks
    STATE / "replay_check.json",                # latest (cr-proxy, chatglm)
]

best: dict[str, dict] = {}
for src in sources:
    if not src.exists():
        print("skip (missing):", src.name)
        continue
    d = json.loads(src.read_text(encoding="utf-8"))
    rows = d.get("results", [])
    print(f"{src.name}: {len(rows)} rows")
    for r in rows:
        host = r.get("host", "?")
        cur = best.get(host)
        if cur is None:
            best[host] = r
        else:
            # keep REPLAY_OK over anything; on equal rank, later source (more recent) wins
            if RANK.get(r.get("verdict"), 9) < RANK.get(cur.get("verdict"), 9):
                best[host] = r
            elif RANK.get(r.get("verdict"), 9) == RANK.get(cur.get("verdict"), 9):
                best[host] = r
            # else: cur is REPLAY_OK and r is not -> keep cur

merged = {
    "generatedAt": json.loads(sources[-1].read_text(encoding="utf-8")).get("generatedAt", ""),
    "question": "does a captured browser request survive being re-sent from python?",
    "results": sorted(best.values(), key=lambda r: r.get("host", "")),
    "replayable": sorted(h for h, r in best.items() if r.get("verdict") == "REPLAY_OK"),
}

out = STATE / "replay_check.json"
out.write_text(json.dumps(merged, indent=1), encoding="utf-8")
print(f"\nmerged -> {out.name}: {len(merged['results'])} rows")
print("REPLAY_OK:", merged["replayable"])
for r in merged["results"]:
    print(f"  {r.get('host','?')[:36]:36s} {r.get('verdict','?')}")
