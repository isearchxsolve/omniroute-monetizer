"""One-off: prove the universal-replay payoff on already-captured sessions.

Loads a session_<host>.json, substitutes the sentinel for a fresh question,
resubmits over the stored cookie, prints ONLY the model answer + shape metadata.
NEVER prints the cookie, token, or full body.
"""
import sys, pathlib
from urllib.parse import urlsplit

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from universal_replay import UniversalSessionClient, SessionExpired, ChatError  # noqa: E402

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
REAL_PROMPT = "What is 7 times 8? Reply with only the number, nothing else."
SENTINELS = [
    "Reply exactly one word: Omni.", "Reply exactly one word: Omni",
    "Reply exactly one word : Omni.", "Reply exactly one word : Omni", "Hi", "Hello",
]

for fn in ("session_plai_chat.json", "session_creen_ai.json"):
    p = SECRETS / fn
    print(f"\n=== {fn} ===")
    if not p.exists():
        print("  MISSING"); continue
    try:
        c = UniversalSessionClient(p)
    except Exception as e:
        print(f"  LOAD_FAIL {type(e).__name__}: {str(e)[:140]}")
        continue
    body = c.base_body or ""
    found = next((s for s in SENTINELS if s in body), None)
    print(f"  host={urlsplit(c.url).hostname} method={c.method} body_len={len(body)}")
    print(f"  sentinel_in_body={'YES ' + repr(found) if found else 'NO (substitution will no-op!)'}")
    try:
        r = c.chat([{"role": "user", "content": REAL_PROMPT}])
        ans = (r.get("text") or "").strip().replace("\n", " ")
        print(f"  answer[:140]={ans[:140]!r}")
        print(f"  -> LIVE + SUBSTITUTION_WORKED={'56' in ans}")
    except SessionExpired as e:
        print(f"  SESSION_EXPIRED: {str(e)[:100]}")
    except ChatError as e:
        print(f"  CHAT_ERROR: {str(e)[:140]}")
    except Exception as e:
        print(f"  ERR {type(e).__name__}: {str(e)[:140]}")
