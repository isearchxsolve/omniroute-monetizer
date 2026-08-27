"""Inspect the auth scheme of the 3 expired seats (groq/cerebras/gemini) to
design credential refresh. Zero cost: reads seat files only. Redacts secrets."""
import sys, json, pathlib, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SECRETS = pathlib.Path("state/secrets")

def redact(v, keep=10):
    v = str(v)
    return v[:keep] + f"...({len(v)} chars)" if len(v) > keep else v

def find_seat(host):
    for p in SECRETS.glob("session_*.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if raw.get("host") == host and raw.get("recorded_exchange"):
            return p, raw
    return None, None

for host in ("api.groq.com", "chat.cerebras.ai", "gemini.google.com"):
    p, raw = find_seat(host)
    print("=" * 66)
    print(f"HOST: {host}  file: {p.name if p else 'NOT FOUND'}")
    if not raw:
        continue
    ex = raw["recorded_exchange"]
    hdrs = ex.get("request_headers") or {}
    print("url:", ex.get("url", "")[:70])
    # auth-bearing headers
    for k in sorted(hdrs.keys()):
        lk = k.lower()
        if lk in ("authorization", "cookie", "x-api-key", "api-key", "x-auth-token",
                  "x-csrf-token", "x-xsrf-token") or "auth" in lk or "token" in lk:
            print(f"   hdr {k}: {redact(hdrs[k])}")
    # top-level cookie_header
    if "cookie_header" in raw:
        print(f"   cookie_header: {redact(raw['cookie_header'])}")
    # body keys
    body = ex.get("request_body", "")
    try:
        bj = json.loads(body)
        if isinstance(bj, dict):
            print("   body keys:", sorted(bj.keys()))
    except Exception:
        pass
    print()
