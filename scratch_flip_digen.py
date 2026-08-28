"""Flip session_digen_ai.json to api.kind='digen' (stateless graduation, worklog #1131).
Idempotent. Preserves all other keys. Never prints secrets.
"""
import json, pathlib

f = pathlib.Path("state/secrets/session_digen_ai.json")
raw = json.loads(f.read_text(encoding="utf-8-sig"))

api = raw.get("api") or {}
if api.get("kind") == "digen":
    print("SKIP: api.kind already 'digen'")
else:
    api["kind"] = "digen"
    raw["api"] = api
    f.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    print("FLIPPED: api.kind='digen' written to", f.name)

# verify round-trip (no secret values printed)
raw2 = json.loads(f.read_text(encoding="utf-8-sig"))
print("verify: api =", raw2.get("api"))
print("verify: top-level keys =", sorted(raw2.keys()))
print("verify: recorded_job exchanges =", len((raw2.get("recorded_job") or {}).get("exchanges") or []))
