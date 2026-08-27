import json
import pathlib

ROOT = pathlib.Path(".")
REPORT = ROOT / "state" / "browser_replay.json"

if REPORT.exists():
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    for r in data.get("results", []):
        host = r.get("host")
        verdict = r.get("verdict")
        status = r.get("status")
        detail = r.get("detail")
        body_bytes = r.get("bodyBytes", 0)
        print(f"HOST: {host:30s} VERDICT: {verdict:12s} STATUS: {status} BYTES: {body_bytes}")
        if verdict in ("NO_ANSWER", "HTTP_400", "ERROR", "SINGLE_USE"):
            print(f"   Detail: {detail}")
            # If there's recorded body or details in state, let's print snippet
