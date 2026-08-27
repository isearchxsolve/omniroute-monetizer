"""Count tabs discovered across all seat rescan files."""
import json
import pathlib

STATE = pathlib.Path(__file__).resolve().parent / "state"

total = 0
live = 0
for f in sorted(STATE.glob("rescan_*.json")):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{f.name}: ERROR {e}")
        continue
    n = len(data)
    total += n
    nlive = sum(1 for t in data if t.get("live"))
    live += nlive
    print(f"{f.name}: {n} tabs ({nlive} live)")
    # per-port breakdown if present
    ports = {}
    for t in data:
        p = t.get("port", "?")
        ports.setdefault(p, [0, 0])
        ports[p][0] += 1
        if t.get("live"):
            ports[p][1] += 1
    for p, (a, b) in sorted(ports.items(), key=lambda x: str(x[0])):
        print(f"    port {p}: {a} tabs ({b} live)")

print(f"\nTOTAL: {total} tabs discovered, {live} live")
