"""Dry-run stateless-replay test for untested chat seats that already carry a
recorded_exchange. Instantiates UniversalSessionClient directly (does NOT touch
the seat's runtime flag). Reports LIVE / gate honestly with ERR_SIG detection.
"""
import sys, pathlib, re, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")
PROMPT = "Reply exactly one word: Omni."
ERR_SIG = re.compile(
    r"(INVALID_POW|unauthorized|expired|forbidden|invalid token|invalid key|"
    r"invalid jwt|code 4\d\d|code 5\d\d|rate.?limit|captcha|sign in|log ?in|"
    r"authentication|csrf|token mismatch|x-sign|pow|required)", re.I)

CANDIDATES = [
    "session_meta_ai_web.json",
    "session_veoaifree_chat_web.json",
    "session_veoaifree.json",
]

for name in CANDIDATES:
    p = SECRETS / name
    print(f"\n===== {name} =====")
    if not p.exists():
        print("  MISSING")
        continue
    try:
        c = UniversalSessionClient(p)
    except Exception as e:
        print("  CONSTRUCT_FAIL:", type(e).__name__, str(e)[:160])
        continue
    t0 = time.time()
    try:
        out = c.chat([{"role": "user", "content": PROMPT}])
        dt = time.time() - t0
        text = (out.get("text") or "").strip()
        print(f"  HTTP {out.get('status')} in {dt:.1f}s, label={out.get('label')}")
        print(f"  text: {text[:160]!r}")
        if ERR_SIG.search(text) and len(text) < 160:
            print("  VERDICT: FALSE-GREEN (error text) -> GATE")
        elif text:
            print("  VERDICT: LIVE (stateless)")
        else:
            print("  VERDICT: EMPTY -> GATE")
    except SessionExpired as e:
        print(f"  SessionExpired in {time.time()-t0:.1f}s: {str(e)[:160]}")
        print("  VERDICT: AUTH gate")
    except ChatError as e:
        raw = getattr(e, "raw", "") or ""
        st = getattr(e, "status", "")
        print(f"  ChatError in {time.time()-t0:.1f}s: {str(e)[:200]}")
        if st:
            print(f"  status={st}")
        if raw:
            print(f"  raw head: {raw[:200]!r}")
        print("  VERDICT: GATE")
    except Exception as e:
        print(f"  EXC {type(e).__name__} in {time.time()-t0:.1f}s: {str(e)[:200]}")
        print("  VERDICT: GATE/ERROR")
