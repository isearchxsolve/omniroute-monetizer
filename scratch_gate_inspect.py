"""Inspect the three send-time-gated blueprints (deepseek PoW, chatglm 400,
chatx 419) to find what the site adds at send-time that the recorded bytes
lack. Zero cost: reads seat files only."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SECRETS = pathlib.Path("state/secrets")

def find_seat(host):
    for p in SECRETS.glob("session_*.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if raw.get("host") == host and raw.get("recorded_exchange"):
            return p, raw
    return None, None

for host in ("chat.deepseek.com", "chatglm.cn", "chatx.ai"):
    p, raw = find_seat(host)
    print("=" * 70)
    print(f"HOST: {host}  file: {p.name if p else 'NOT FOUND'}")
    if not raw:
        continue
    ex = raw["recorded_exchange"]
    print("url:", ex.get("url"))
    print("method:", ex.get("method"))
    hdrs = ex.get("request_headers") or {}
    print("request_headers keys:", sorted(hdrs.keys()))
    body = ex.get("request_body", "")
    print("body len:", len(body))
    # try to parse body as JSON and show keys
    try:
        bj = json.loads(body)
        print("body JSON keys:", sorted(bj.keys()) if isinstance(bj, dict) else type(bj).__name__)
        # show non-huge values
        for k, v in (bj.items() if isinstance(bj, dict) else []):
            sv = json.dumps(v, ensure_ascii=False)
            print(f"   {k}: {sv[:120]}")
    except Exception:
        print("body (first 300):", body[:300])
    # response shape
    resp = ex.get("response_body", "")
    print("response (first 200):", str(resp)[:200])
    print()
