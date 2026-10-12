#!/usr/bin/env python3
"""ws_replay_probe.py -- stateless websocket replay verdict for one session file.

Reads a session_<id>_ws.json blueprint (modality: websocket, recorded_ws with
url + frames_sent + frames_received), replaces the sentinel with the Law-3
arithmetic probe, replays over websocket-client, and prints WS_REPLAY_OK ONLY
when the model answered the computed number (same strict verdict as HTTP).

Prints the replay_check-style detail line; exit 0 on OK.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ws_replay import WebSocketSessionClient  # noqa: E402
from veoaifree_chat_client import ChatError  # noqa: E402

PROBE_PROMPT = "What is 58 times 3? Reply with only the number."
EXPECT = "174"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", required=True, help="path to session_<id>_ws.json")
    ap.add_argument("--prompt", default=PROBE_PROMPT)
    ap.add_argument("--expect", default=EXPECT)
    a = ap.parse_args()

    started = time.perf_counter()
    try:
        client = WebSocketSessionClient(path=a.session)
        res = client.chat([{"role": "user", "content": a.prompt}])
        text = str((res or {}).get("text") or "")
        raw = str((res or {}).get("raw") or "")
        ms = round((time.perf_counter() - started) * 1000)
        import re as _re
        if _re.fullmatch(r"\s*" + _re.escape(a.expect) + r"\s*[.!]?\s*", text or ""):
            print(f"WS_REPLAY_OK {ms}ms answer={text.strip()[:60]}")
            return 0
        if _re.match(r"\s*" + _re.escape(a.expect) + r"(?!\d)", text or ""):
            print(f"WS_REPLAY_OK {ms}ms answer-opens={text.strip()[:60]}")
            return 0
        print(f"WS_NO_ANSWER {ms}ms text={text.strip()[:120]!r}")
        return 1
    except ChatError as e:
        ms = round((time.perf_counter() - started) * 1000)
        print(f"WS_{getattr(e, 'args', [''])[0] if e.args else 'ERROR'} {ms}ms {str(e)[:140]}")
        return 1
    except Exception as e:
        ms = round((time.perf_counter() - started) * 1000)
        print(f"WS_ERROR {ms}ms {type(e).__name__}: {str(e)[:140]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())