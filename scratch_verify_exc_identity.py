"""Verify exception class identity is unified across all pool adapters (worklog #1109)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import veoaifree_chat_client as vc
import veo_session_replay as vs
import universal_replay as ur
import video_universal_replay as vur
import chrome_replay_client as crc
import chrome_video_client as cvc
import digen_session_replay as dsr
import rtst_api_client as rtst
import youcom_api_client as yc
import session_pool as sp

canon_chat = vc.ChatError
canon_exp = vs.SessionExpired

checks = [
    ("universal_replay.ChatError", ur.ChatError),
    ("universal_replay.SessionExpired", ur.SessionExpired),
    ("video_universal_replay.ChatError", vur.ChatError),
    ("video_universal_replay.SessionExpired", vur.SessionExpired),
    ("chrome_replay_client.ChatError", crc.ChatError),
    ("chrome_replay_client.SessionExpired", crc.SessionExpired),
    ("chrome_video_client.ChatError", cvc.ChatError),
    ("chrome_video_client.SessionExpired", cvc.SessionExpired),
    ("digen_session_replay.ChatError", dsr.ChatError),
    ("digen_session_replay.SessionExpired", dsr.SessionExpired),
    ("rtst_api_client.ChatError", rtst.ChatError),
    ("rtst_api_client.SessionExpired", rtst.SessionExpired),
    ("youcom_api_client.ChatError", yc.ChatError),
    ("youcom_api_client.SessionExpired", yc.SessionExpired),
    ("session_pool.ChatError", sp.ChatError),
    ("session_pool.SessionExpired", sp.SessionExpired),
]

ok = True
for name, cls in checks:
    if name.endswith("ChatError"):
        good = cls is canon_chat
    else:
        good = cls is canon_exp
    print(f"{'OK ' if good else 'BAD'} {name} -> {cls.__module__}.{cls.__name__}")
    ok = ok and good

# SessionExpired must be a subclass of ChatError so `except ChatError` catches it too
print(f"{'OK ' if issubclass(canon_exp, canon_chat) else 'BAD'} SessionExpired is subclass of ChatError")

# Simulate: a 429-style raise from universal_replay must be caught by session_pool's except
try:
    raise ur.ChatError("HTTP_ERROR", "HTTP Error 429: ")
except sp.ChatError as e:
    print(f"OK  universal_replay 429 caught by session_pool except ChatError: {e}")
except Exception as e:
    print(f"BAD universal_replay 429 ESCAPED: {type(e).__name__}: {e}")
    ok = False

try:
    raise ur.SessionExpired("AUTH", "Auth rejected")
except sp.SessionExpired as e:
    print(f"OK  universal_replay SessionExpired caught by session_pool: {e}")
except Exception as e:
    print(f"BAD universal_replay SessionExpired ESCAPED: {type(e).__name__}: {e}")
    ok = False

print("\nRESULT:", "ALL_UNIFIED" if ok else "STILL_BROKEN")
