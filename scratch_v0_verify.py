import json, sys, pathlib, re, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

p = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_v0_app.json")
d = json.loads(p.read_text(encoding="utf-8-sig"))
rx = d.get("recorded_exchange") or {}
print("url:", rx.get("url"))
print("method:", rx.get("method"))
body = rx.get("request_body", "")
print("body len:", len(body))
print("body head:", body[:300].replace("\n", " "))
print("sentinel in body?", d.get("sentinel", "") in body)
print("cookie len:", len(d.get("cookie_header", "")))
print("headers:", [k for k in rx.get("request_headers", {}) if not k.startswith(":")])

print("\n--- stateless replay test ---")
ERR_SIG = re.compile(r"(unauthorized|expired|forbidden|invalid|rate.?limit|captcha|sign in|log ?in|csrf|error)", re.I)
try:
    c = UniversalSessionClient(p)
    t0 = time.time()
    out = c.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
    dt = time.time() - t0
    text = (out.get("text") or "").strip()
    print(f"HTTP {out.get('status')} in {dt:.1f}s label={out.get('label')}")
    print(f"text: {text[:200]!r}")
    if ERR_SIG.search(text) and len(text) < 160:
        print("VERDICT: FALSE-GREEN (error text) -> GATE")
    elif text:
        print("VERDICT: LIVE (stateless)")
    else:
        print("VERDICT: EMPTY -> GATE")
except SessionExpired as e:
    print("SessionExpired:", str(e)[:160]); print("VERDICT: AUTH gate")
except ChatError as e:
    raw = getattr(e, "raw", "") or ""
    st = getattr(e, "status", "")
    print("ChatError:", str(e)[:200])
    if st: print("status:", st)
    if raw: print("raw head:", raw[:200])
    print("VERDICT: GATE")
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:200]); print("VERDICT: GATE/ERROR")
