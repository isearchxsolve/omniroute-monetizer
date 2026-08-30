#!/usr/bin/env python3
"""Copilot live-tab adapter -- the browser is the client.

Drives the open Copilot tab on :9222 through its own composer (focus, type, send)
and reads the assistant's reply from the DOM. No websocket replay, no TLS-fingerprint
wall: Chrome's own connection is trusted. The reply renders in the last
[role="article] element after the message count grows.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capture_sessions_cdp import CDP, JS_FOCUS_COMPOSER, JS_READ_ACTIVE, JS_SEND, targets  # noqa: E402

PORT = 9222
PROBE = "Reply with only the number: 41 + 17"


def find_tab(port: int):
    return next((t for t in targets(port) if t.get("type") == "page"
                 and "copilot.microsoft.com" in (t.get("url") or "")), None)


def chat(cdp, prompt: str, wait_s: int = 60) -> str:
    try:
        cdp.call("Page.bringToFront")
    except Exception:
        pass
    time.sleep(0.8)

    # ensure we are on a chat surface with a composer
    cur = ""
    try:
        cur = cdp.evaluate("location.href") or ""
    except Exception:
        cur = ""
    if "/chats/" not in cur and "/tasks/" not in cur:
        cdp.call("Page.navigate", {"url": "https://copilot.microsoft.com/chats"}, timeout=30)
        time.sleep(10)

    cdp.evaluate(JS_FOCUS_COMPOSER)
    time.sleep(0.3)
    cdp.call("Input.insertText", {"text": prompt})
    time.sleep(0.4)
    before = cdp.evaluate("(() => document.querySelectorAll('[role=\"article\"]').length)()") or 0
    try:
        cdp.evaluate(JS_SEND.replace("__CLICK__", "true"))
    except Exception as e:
        raise RuntimeError(f"send failed: {e}") from e

    deadline = time.monotonic() + wait_s
    last_n = before
    prev = ""
    stable = 0
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            n = cdp.evaluate("(() => document.querySelectorAll('[role=\"article\"]').length)()") or 0
            last = cdp.evaluate(
                "(() => {const a=[...document.querySelectorAll('[role=\"article\"]')];"
                "return a.length ? (a[a.length-1].innerText||'') : '';})()") or ""
        except Exception:
            continue
        if n > last_n:
            last_n = n
        norm = " ".join(last.split()).strip()
        # the user's own bubble echoes the prompt ("You said <prompt>") -- never the reply
        if not norm or (norm.lower().startswith("you said") and norm.lower().find(" ".join(prompt.split()).lower()) >= 0):
            prev = ""
            stable = 0
            continue
        if norm == prev:
            stable += 1
        else:
            stable = 0
        prev = norm
        if stable >= 2:
            return norm
    raise TimeoutError(f"no assistant reply within {wait_s}s (articles {before}->{last_n})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prompt", default=PROBE)
    ap.add_argument("--wait", type=int, default=60)
    a = ap.parse_args()

    tab = find_tab(PORT)
    if not tab:
        print("no copilot tab on :9222", file=sys.stderr)
        return 1
    cdp = CDP(tab["webSocketDebuggerUrl"])
    try:
        reply = chat(cdp, a.prompt, a.wait)
    except Exception as e:
        print(f"chat error: {e}", file=sys.stderr)
        return 2
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
