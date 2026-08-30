#!/usr/bin/env python3
"""Navigate exactly one attested dedicated-seat tab behind visual gates.

This is deliberately narrower than harness_all_tabs.py.  It makes a single
blank/controlled tab usable for reconciliation without permitting a fleet run:

1. Re-attest the CDP listener is an automation profile.
2. Capture and save a pre-navigation screenshot of the exact target.
3. Navigate that target to one supplied HTTPS URL and wait for metadata to settle.
4. Capture and save a post-navigation screenshot.

It does not evaluate page JavaScript, inspect cookies, focus the target, click
anything, type credentials, submit a prompt, capture a provider request, or
perform SSO.  A later, separately reviewed action must inspect the post image
before any SSO control can be considered.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tab_graduation_sweep import (  # noqa: E402
    CANDIDATES,
    SafetyRefusal,
    assert_automation_seat,
    capture_target_screenshot,
)


def exact_target(port: int, target_id: str) -> dict:
    rows = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=15).read().decode("utf-8", "replace"))
    row = next((item for item in rows if item.get("id") == target_id and item.get("type") == "page"), None)
    if not row:
        raise SafetyRefusal("exact page target vanished before navigation")
    return row


def navigate_and_settle(port: int, target_id: str, url: str, wait: float) -> str:
    row = exact_target(port, target_id)
    ws_url = str(row.get("webSocketDebuggerUrl") or "")
    if not ws_url.startswith(f"ws://127.0.0.1:{port}/"):
        raise SafetyRefusal("exact page target has no local DevTools websocket")
    import websocket
    ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            ws.settimeout(max(0.5, deadline - time.monotonic()))
            reply = json.loads(ws.recv())
            if reply.get("id") == 1:
                if reply.get("error"):
                    raise SafetyRefusal(f"Page.navigate refused: {reply['error']}")
                break
        else:
            raise SafetyRefusal("Page.navigate did not acknowledge within 30 seconds")
    finally:
        ws.close()

    deadline, last, stable = time.monotonic() + wait, "", 0
    while time.monotonic() < deadline:
        time.sleep(1.5)
        current = str(exact_target(port, target_id).get("url") or "")
        if current and current == last:
            stable += 1
            if stable >= 2:
                return current
        else:
            last, stable = current, 0
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--target", required=True, help="exact existing DevTools target id")
    parser.add_argument("--url", required=True, help="one HTTPS page URL")
    parser.add_argument("--wait", type=float, default=25.0)
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        parser.error("--url must be a credential-free HTTPS URL")

    assert_automation_seat(args.port)
    before = capture_target_screenshot(args.port, args.target)
    candidate = CANDIDATES / f"{args.port}_{args.target[:16].lower()}"
    pre = candidate / "pre_navigate.png"
    shutil.copyfile(before, pre)
    final = navigate_and_settle(args.port, args.target, args.url, args.wait)
    after = capture_target_screenshot(args.port, args.target)
    post = candidate / "post_navigate.png"
    shutil.copyfile(after, post)
    report = candidate / "navigation_gate.json"
    report.write_text(json.dumps({
        "port": args.port, "targetId": args.target,
        "requestedHost": parsed.hostname, "finalHost": urllib.parse.urlsplit(final).hostname or "",
        "preScreenshot": str(pre), "postScreenshot": str(post),
        "result": "NAVIGATED_AWAITING_VISUAL_REVIEW",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"pre screenshot : {pre}")
    print(f"final host     : {urllib.parse.urlsplit(final).hostname or '(none)'}")
    print(f"post screenshot: {post}")
    print("result         : NAVIGATED_AWAITING_VISUAL_REVIEW (no SSO/click/evaluation performed)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyRefusal as exc:
        raise SystemExit(f"reconciliation refused: {exc}") from exc
