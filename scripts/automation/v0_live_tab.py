#!/usr/bin/env python3
"""V0 live-tab adapter -- the browser is the client.

v0.app's chat POST returns only an "ok" ack and silently DROPS sends whose
`x-is-human` anti-bot JWT (client-minted JWE) is stale, so recorded-jar replay
cannot deliver the answer. The live tab mints everything itself: this adapter
drives the tab's ProseMirror composer (clear -> insertText -> Enter) and polls
the chat-latest endpoint IN PAGE CONTEXT for an assistant message created after
the send, extracting the reply from v0's message-binary-format tree.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capture_sessions_cdp import CDP, targets  # noqa: E402

PORT = 9222
PROBE = "Reply with only the number: 41 + 17"


def find_tab(port: int):
    return next((t for t in targets(port) if t.get("type") == "page"
                 and "v0.app" in (t.get("url") or "")), None)


def _js_str(s: str) -> str:
    import json
    return json.dumps(s)


def _url_q(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s, safe="")


def submit(cdp, prompt: str) -> None:
    cdp.call("Page.bringToFront")
    time.sleep(0.8)
    for attempt in range(3):
        # proven path (no mouse click -- execCommand clear + insertText + Enter)
        cdp.evaluate(r"""
(() => {
  const ed = document.querySelector('.tiptap.ProseMirror, [contenteditable="true"]');
  if (!ed) return 'no-editor';
  ed.focus();
  document.execCommand('selectAll');
  document.execCommand('delete');
  return 'cleared';
})()
""")
        time.sleep(0.3)
        cdp.call("Input.insertText", {"text": prompt})
        time.sleep(0.5)
        got = str(cdp.evaluate(
            "(document.querySelector('.tiptap.ProseMirror, [contenteditable=\"true\"]')||{}).innerText || ''"))
        if " ".join(got.split()) != " ".join(prompt.split()):
            time.sleep(1)
            continue
        cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter",
                                            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter",
                                            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        time.sleep(1.5)
        left = str(cdp.evaluate(
            "(document.querySelector('.tiptap.ProseMirror, [contenteditable=\"true\"]')||{}).innerText || ''"))
        if not left.strip():
            return
        time.sleep(1)
    raise RuntimeError("could not submit the prompt into the v0 composer after 3 attempts")


def poll_reply(cdp, wait_s: int, chat_id: str) -> str:
    from datetime import datetime
    cutoff_ms = int(time.time() * 1000) - 5000
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        time.sleep(4)
        try:
            data = cdp.evaluate(
                "fetch('/api/chat/chat/latest?chatId=" + _url_q(chat_id)
                + "&lastSyncedAt=0',{credentials:'include'}).then(r=>r.json())", timeout=20)
        except Exception:
            continue
        msgs = (((data or {}).get("value") or {}).get("newMessages")) or []
        assistants = [m for m in msgs if isinstance(m, dict) and m.get("role") == "assistant"]
        if not assistants:
            continue
        latest = assistants[-1]
        created = str(latest.get("createdAt") or "")
        try:
            created_ms = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            created_ms = 0
        if created_ms and created_ms < cutoff_ms:
            continue                      # newest assistant message predates our send
        if latest.get("isContentLoading") or latest.get("streaming"):
            continue                      # still generating
        text = _v0_text(latest.get("content")).strip()
        if text:
            return text
    raise TimeoutError(f"no new v0 reply within {wait_s}s")


def _v0_text(node) -> str:
    if isinstance(node, list):
        if len(node) >= 3 and node[0] == "text" and isinstance(node[2], str):
            return node[2]
        return "".join(_v0_text(c) for c in node)
    if isinstance(node, dict):
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            return node["text"]
        return "".join(_v0_text(v) for v in node.values())
    return ""


def chat(cdp, prompt: str, wait_s: int = 90) -> str:
    chat_id = _chat_id_from_tab(cdp)
    if not chat_id:
        raise RuntimeError("cannot derive chatId from the v0 tab url")
    # v0 rate-limits rapid sends (429 on /chat/api/chat) and silently drops the
    # message even though /chat/api/send still acks "ok". On a dropped send the
    # poll times out -- so retry with a growing backoff until one lands.
    backoff = 0
    for attempt in range(3):
        if backoff:
            time.sleep(backoff)
            # re-derive: the tab url re-keys on every successful submit
            chat_id = _chat_id_from_tab(cdp) or chat_id
        try:
            submit(cdp, prompt)
            return poll_reply(cdp, 25, chat_id)
        except (TimeoutError, RuntimeError):
            # dropped send (rate limit) or flaky Enter -- backoff and retry
            backoff = backoff * 2 + 30 if backoff else 30
    raise TimeoutError(f"v0 send kept being rate-limited after 3 backoff retries")


def _chat_id_from_tab(cdp) -> str:
    """Raw chat id from the tab url. v0 slugifies the url after a submission
    (/chat/omni-kJUe2xY1JpE) but the API only accepts the bare id."""
    import urllib.parse
    path = urllib.parse.urlsplit(str(cdp.evaluate("location.href"))).path
    seg = [s for s in path.split("/") if s]
    if not seg:
        return ""
    last = seg[-1]
    return last.rsplit("-", 1)[-1] if "-" in last else last


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prompt", default=PROBE)
    ap.add_argument("--wait", type=int, default=90)
    a = ap.parse_args()

    tab = find_tab(PORT)
    if not tab:
        print("no v0.app tab on :9222", file=sys.stderr)
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
