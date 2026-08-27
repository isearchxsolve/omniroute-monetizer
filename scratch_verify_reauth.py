"""Verify the 3 refreshed seats via stateless replay (UniversalSessionClient).

Prints LIVE / AUTH-EXPIRED / GATE verdict per seat. Uses the same ERR_SIG
detection as the earlier sweep so error-JSON is never counted as success.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from universal_replay import UniversalSessionClient  # noqa: E402

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

ERR_SIG = re.compile(
    r"INVALID_POW|unauthorized|unauthenticated|expired|forbidden|invalid.{0,20}(token|key|jwt|session|credential)"
    r"|code.{0,3}4\d\d|code.{0,3}5\d\d|rate.?limit|captcha|sign.?in|log.?in|login.?wall|access.?denied"
    r"|please.{0,20}(sign|log)|session.{0,20}(expired|invalid)|token.{0,20}(expired|invalid|revoked)",
    re.I,
)

SEATS = [
    "session_groq_chat.json",
    "session_cerebras_inference_chat.json",
    "session_google_gemini_web.json",
]


def verify(name: str):
    path = SEATDIR / name
    t0 = time.time()
    try:
        client = UniversalSessionClient(str(path))
        resp = client.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
        dt = time.time() - t0
        text = ""
        if isinstance(resp, dict):
            text = resp.get("content") or resp.get("text") or json.dumps(resp)[:300]
        else:
            text = str(resp)
        text = text or ""
        if ERR_SIG.search(text):
            print(f"  {name}: AUTH-EXPIRED/GATE ({dt:.1f}s) -> {text[:160]!r}")
            return "GATE"
        if not text.strip():
            print(f"  {name}: EMPTY ({dt:.1f}s) -> resp={str(resp)[:160]!r}")
            return "EMPTY"
        print(f"  {name}: LIVE ({dt:.1f}s) -> {text[:120]!r}")
        return "LIVE"
    except Exception as e:
        dt = time.time() - t0
        msg = str(e)
        verdict = "AUTH-EXPIRED" if ERR_SIG.search(msg) else "ERROR"
        print(f"  {name}: {verdict} ({dt:.1f}s) -> {msg[:200]!r}")
        return verdict


def main():
    results = {}
    for name in SEATS:
        results[name] = verify(name)
    print("\nSUMMARY:")
    for name, v in results.items():
        print(f"  {name}: {v}")
    live = sum(1 for v in results.values() if v == "LIVE")
    print(f"\n{live}/{len(SEATS)} LIVE")


if __name__ == "__main__":
    main()
