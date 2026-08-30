#!/usr/bin/env python3
"""Puter live-tab adapter -- the browser is the client.

Drives the open puter.com tab on :9222 through its own puter.js SDK
(`puter.ai.chat`), which sends with the tab's own session token. No cookie-jar
replay, no auth reconstruction: Puter's anonymous-account session lives in
localStorage (`auth_token_v2`) and is invisible to cookie-based readiness
probes, but the SDK in the page context uses it natively.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capture_sessions_cdp import CDP, targets  # noqa: E402

PORT = 9222
PROBE = "Reply with only the number: 41 + 17"


def find_tab(port: int):
    return next((t for t in targets(port) if t.get("type") == "page"
                 and "puter.com" in (t.get("url") or "")), None)


def chat(cdp, prompt: str, wait_s: int = 60) -> str:
    try:
        cdp.call("Page.bringToFront")
    except Exception:
        pass

    has = cdp.evaluate("(() => ({ok: !!(window.puter && window.puter.ai"
                       " && typeof window.puter.ai.chat === 'function')}))()")
    if not (has or {}).get("ok"):
        cdp.call("Page.navigate", {"url": "https://puter.com/"}, timeout=30)
        time.sleep(10)
        has = cdp.evaluate("(() => ({ok: !!(window.puter && window.puter.ai"
                           " && typeof window.puter.ai.chat === 'function')}))()")
        if not (has or {}).get("ok"):
            raise RuntimeError("puter.js SDK not available on the tab")

    cdp.evaluate(
        "window.__omni_result = null; window.__omni_err = null;"
        "window.puter.ai.chat(" + json.dumps(prompt) + ")"
        ".then(r => { try { window.__omni_result = (r && r.message && r.message.content)"
        " ? r.message.content : (typeof r === 'string' ? r : JSON.stringify(r).slice(0, 500)); }"
        " catch (e) { window.__omni_result = JSON.stringify(r).slice(0, 500); } })"
        ".catch(e => { window.__omni_err = String(e).slice(0, 300); });"
    )

    deadline = time.monotonic() + wait_s
    result = None
    while time.monotonic() < deadline:
        time.sleep(2)
        result = cdp.evaluate("(() => ({r: window.__omni_result, e: window.__omni_err}))()")
        if result and (result.get("r") or result.get("e")):
            break
    if not result:
        raise TimeoutError(f"no sdk answer within {wait_s}s")
    if result.get("e"):
        raise RuntimeError(f"puter.ai.chat error: {result['e']}")
    reply = (result.get("r") or "").strip()
    if not reply:
        raise RuntimeError("empty reply")
    return reply


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prompt", default=PROBE)
    ap.add_argument("--wait", type=int, default=60)
    a = ap.parse_args()

    tab = find_tab(PORT)
    if not tab:
        print("no puter.com tab on :9222", file=sys.stderr)
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
