"""Inspect the Felo recorded exchange structure (secrets redacted) + last raw replay reply."""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent
p = ROOT / "state/secrets/session_felo_ai_web.json"
d = json.loads(p.read_text(encoding="utf-8"))
ex = d.get("recorded_exchange") or {}
print("host:", d.get("host"))
print("url:", ex.get("url"))
print("method:", ex.get("method"))
hdrs = ex.get("request_headers") or {}
print("headers:", sorted(hdrs.keys()))
body = ex.get("request_body") or ""
print("body len:", len(body))
# redact anything token-ish, print structure
try:
    jb = json.loads(body)
    def redact(o):
        if isinstance(o, dict):
            return {k: ("***" if any(s in k.lower() for s in ("token", "key", "auth", "secret")) else redact(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [redact(x) for x in o]
        if isinstance(o, str) and len(o) > 60:
            return o[:40] + "...(%d chars)" % len(o)
        return o
    print("body json:")
    print(json.dumps(redact(jb), indent=1, ensure_ascii=False))
except Exception as e:
    print("body not json:", e, body[:300])

# raw replay reply if kept
raw_dir = ROOT / "state/replay_raw"
if raw_dir.exists():
    hits = sorted(raw_dir.glob("*felo*"))
    for h in hits[-3:]:
        print("\n--- raw:", h.name, "---")
        print(h.read_text(encoding="utf-8", errors="replace")[:800])
