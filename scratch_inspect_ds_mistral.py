"""Inspect DeepSeek and Mistral recorded exchanges + live rejection bodies."""
import json, pathlib, sys, requests
sys.path.insert(0, "scripts/automation")

ROOT = pathlib.Path(__file__).resolve().parent

for fname in ["session_deepseek_chat.json", "session_mistral_le_chat.json"]:
    p = ROOT / "state/secrets" / fname
    d = json.loads(p.read_text(encoding="utf-8"))
    ex = d.get("recorded_exchange") or {}
    print(f"\n{'='*60}\n{fname}")
    print("host:", d.get("host"))
    print("url:", ex.get("url"))
    print("method:", ex.get("method"))
    hdrs = ex.get("request_headers") or {}
    print("headers:", sorted(hdrs.keys()))
    body = ex.get("request_body") or ""
    print("body len:", len(body))
    try:
        jb = json.loads(body)
        def redact(o, depth=0):
            if isinstance(o, dict):
                return {k: ("***" if any(s in k.lower() for s in ("token", "key", "auth", "secret", "sign", "hash")) else redact(v, depth+1)) for k, v in o.items()}
            if isinstance(o, list):
                return [redact(x, depth+1) for x in o[:3]] + (["..."] if len(o) > 3 else [])
            if isinstance(o, str) and len(o) > 80:
                return o[:50] + f"...({len(o)} chars)"
            return o
        print("body json:")
        print(json.dumps(redact(jb), indent=1, ensure_ascii=False)[:2000])
    except Exception as e:
        print("body not json:", e, body[:200])

    # Now replay once and capture raw rejection
    from universal_replay import UniversalSessionClient
    import requests as _rq
    captured = {}
    _orig = _rq.Session.request
    def spy(self, method, url, **kw):
        r = _orig(self, method, url, **kw)
        captured["status"] = r.status_code
        captured["body"] = r.text[:1500]
        return r
    _rq.Session.request = spy
    try:
        client = UniversalSessionClient(str(p))
        res = client.chat([{"role": "user", "content": "Reply with only the number: 41 + 17"}])
        print("ANSWER:", str(res)[:200])
    except Exception as e:
        print("EXC:", type(e).__name__, str(e)[:200])
    _rq.Session.request = _orig
    print("raw status:", captured.get("status"))
    print("raw body:", captured.get("body", "")[:800])
