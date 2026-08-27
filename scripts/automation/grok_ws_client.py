"""grok_ws_client.py — REFERENCE ONLY: hand-replayed grok websocket protocol (NOT the runtime).

!!! DOCTRINE CORRECTION (2026-08-28, operator) — READ BEFORE TOUCHING !!!
This file hand-speaks grok's PROVIDER protocol (session.create frames, chunk channels, the
`uid` device-identity trick, session.moved handling). That is "playing the provider" —
reverse-engineering / copycatting the provider's contract. The doctrine's architecture is to
BE CHROME, not the provider: provide the Chrome blueprint (a real V8 engine via
Selenium/Playwright) and let the provider's own JS land on it and play by itself. The provider
IS the contract; we are only the environment. "What does Chrome have that I don't?" — a real
V8 engine; my Python replay has none, which is why I was forced to reverse-engineer. That
reverse-engineering is the symptom of missing the blueprint.

Therefore this client is NOT wired into session_pool and MUST NOT be re-wired. grok's runtime
is the Chrome-blueprint path (ChromeReplayClient / Selenium-driven V8), where grok's own JS
opens its own websocket and runs its own protocol by itself. Kept only as proof that the
captured websocket blueprint (state/secrets/session_grok_ws.json) is complete.

Doctrine 3a (AGENTS.md): "Why can Chrome do it? Why can't I?" Chrome chats with grok over a
websocket, so the capability EXISTS with the cookie in hand. The gap was only that the capture
recorded one HTTP POST while grok speaks a websocket. This client IS that websocket transport,
built from the blueprint in state/secrets/session_grok_ws.json (capture_websocket_cdp.py).

PROTOCOL (fully decoded from the capture, proven LIVE 2026-08-28):
  * Connect  wss://grok.com/ws/mgw/?uid=<uid>  with Cookie + Origin + Chrome UA.
    THE KEY DISCOVERY: the `uid` query param is the DEVICE identity. Reusing Chrome's captured
    uid makes Python the same device -> the server hands us the session (session.created).
    A FRESH uid is rejected with `session.moved` + close (the account's session is already owned
    by the captured device). So we ALWAYS reuse the captured uid. No need to suspend Chrome,
    no grace period, no tab manipulation.
  * sent[0]  session.create  {session_id:<conv>, event.session:{model, x_grok:{...}}}
    For a stateless per-call client we use a FRESH conversation_id with load_existing:false and
    parent_response_id:null — no history/leaf tracking needed (proven to answer).
  * recv     session.created -> (we are owner)
  * sent     response.create  {item:{role:user, x_grok:{input_chunks:[{text:{text:<prompt>}}]}},
                               parent_response_id:null}
  * recv     response.chunk frames stream the answer. The authoritative text is in
             chunk.text where chunk.text.channel == "CHANNEL_ASSISTANT_RESPONSE".
             ("CHANNEL_ASSISTANT_NOTETAKER_HEADER" = "Thinking about your request" noise — skip.)
             Terminal: response.done (response.status == completed).

Contract (matches session_pool): __init__(secret=path|dict); .chat(messages, model=None, **kw)
-> {"text","label","status","raw"}. Raises canonical SessionExpired / ChatError (never redefined).
Parallel-safe: each call opens its own websocket, no shared browser, no global lock.
"""
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import websocket as _wsc

try:
    from veoaifree_chat_client import ChatError          # canonical
    from veo_session_replay import SessionExpired        # canonical (subclass of ChatError)
except ImportError:
    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
    from veoaifree_chat_client import ChatError
    from veo_session_replay import SessionExpired

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
ORIGIN = "https://grok.com"
ANSWER_CHANNEL = "CHANNEL_ASSISTANT_RESPONSE"

# Error signatures that must never be counted as a successful answer (Law 3).
_ERR_SIG = re.compile(
    r"(sign ?in|log ?in|unauthenticated|unauthorized|rate.?limit|quota|expired|"
    r"forbidden|captcha|cloudflare|attention required|upgrade to|paywall|"
    r"session.moved|something went wrong|try again later)", re.I)


class GrokWsClient:
    """Stateless grok.com websocket client. Constructor matches the pool contract: (secret=path|dict)."""

    def __init__(self, secret):
        if isinstance(secret, (str, Path)):
            self._src = Path(secret)
            with open(secret, "r", encoding="utf-8-sig") as f:
                self.raw = json.load(f)
        else:
            self._src = None
            self.raw = secret

        self.cookie_header = self.raw.get("cookie_header", "")
        rws = self.raw.get("recorded_ws") or {}
        self._ws_url = rws.get("url", "")
        # The uid in the captured ws url is the device identity we must reuse.
        self._uid = self._ws_url.split("uid=")[1] if "uid=" in self._ws_url else str(uuid.uuid4())
        # Recover model + protocol_capabilities from the captured session.create frame.
        self._model = "fast"
        self._caps: List[str] = []
        for f in rws.get("frames_sent", []):
            try:
                o = json.loads(f)
            except Exception:
                continue
            ev = o.get("event") or {}
            if ev.get("type") == "session.create":
                sess = ev.get("session") or {}
                self._model = sess.get("model") or self._model
                self._caps = (sess.get("x_grok") or {}).get("protocol_capabilities", []) or self._caps
                break
        if not self.cookie_header:
            raise ChatError("NO_COOKIE", "seat has no cookie_header (re-capture with capture_websocket_cdp.py)")
        if not self._ws_url:
            raise ChatError("NO_WS", "seat has no recorded_ws.url (re-capture with capture_websocket_cdp.py)")

    # ------------------------------------------------------------------ transport
    def _connect(self):
        url = f"wss://grok.com/ws/mgw/?uid={self._uid}"
        try:
            return _wsc.create_connection(
                url, timeout=30, suppress_origin=True, max_size=64 * 1024 * 1024,
                header=["Cookie: " + self.cookie_header, "Origin: " + ORIGIN,
                        "User-Agent: " + UA])
        except Exception as e:
            raise ChatError("WS_CONNECT", f"websocket connect failed: {type(e).__name__}: {e}")

    @staticmethod
    def _recv(ws, timeout=10) -> Optional[dict]:
        ws.settimeout(timeout)
        try:
            return json.loads(ws.recv())
        except _wsc.WebSocketTimeoutException:
            return None
        except Exception:
            return None

    @staticmethod
    def _send(ws, obj) -> None:
        ws.send(json.dumps(obj))

    # ------------------------------------------------------------------ public API
    def chat(self, messages, model=None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        # Single-exchange replay like the other adapters: use the last user turn as the prompt.
        prompt = None
        for m in reversed(messages):
            if (m.get("role") or "").lower() == "user":
                prompt = m.get("content")
                break
        if prompt is None:
            prompt = messages[-1].get("content")
        if not prompt or not str(prompt).strip():
            raise ChatError("EMPTY_PROMPT", "empty prompt")
        prompt = str(prompt)

        use_model = model or self._model
        ws = self._connect()
        try:
            return self._exchange(ws, prompt, use_model)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ the exchange
    def _exchange(self, ws, prompt: str, use_model: str) -> Dict[str, Any]:
        conv = str(uuid.uuid4())                       # fresh conversation each call
        t0 = time.time()

        # 1) session.create — become the owner of this device's realtime session.
        self._send(ws, {"session_id": conv, "event": {
            "type": "session.create", "event_id": f"evt_init_{uuid.uuid4()}",
            "session": {"model": use_model, "x_grok": {
                "protocol_capabilities": self._caps,
                "conversation_id": conv, "load_existing": False, "use_chunk": True,
                "enable_side_by_side": True, "force_side_by_side": False,
                "enable_image_generation": True, "image_generation_count": 2,
                "disable_text_follow_ups": False, "disable_artifact": True,
                "force_concise": False}}}})

        created = False
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            m = self._recv(ws, 5)
            if m is None:
                continue
            ev = m.get("event") or {}
            typ = ev.get("type")
            if typ == "session.created":
                created = True
                break
            if typ == "session.moved":
                # The account's session is owned by another device and our uid was not accepted
                # as that device — treat as expired so the pool fails over / flags re-capture.
                raise SessionExpired("SESSION_MOVED",
                                     "grok realtime session owned by another device (uid not accepted)")
            if typ == "error":
                raise ChatError("SESSION_ERROR", json.dumps(ev)[:200])
        if not created:
            raise ChatError("NO_SESSION", "no session.created within 15s")

        # 2) response.create — send the user prompt.
        self._send(ws, {"session_id": conv, "event": {
            "type": "response.create", "event_id": f"evt_resp_{int(time.time() * 1000)}",
            "item": {"type": "message", "role": "user",
                     "x_grok": {"client_message_id": str(uuid.uuid4()),
                                "input_chunks": [{"text": {"text": prompt}}]}},
            "parent_response_id": None}})

        # 3) Stream the answer from response.chunk frames.
        parts: List[str] = []
        final_text: Optional[str] = None
        done = False
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not done:
            m = self._recv(ws, 10)
            if m is None:
                continue
            ev = m.get("event") or {}
            typ = ev.get("type")
            if typ == "response.chunk":
                tx = (ev.get("chunk") or {}).get("text") or {}
                if tx.get("channel") == ANSWER_CHANNEL and tx.get("text"):
                    parts.append(tx["text"])
            elif typ in ("response.output_item.done", "conversation.history.item"):
                item = ev.get("item") or {}
                if item.get("role") == "assistant":
                    for ch in (item.get("x_grok") or {}).get("output_chunks", []):
                        tx = ch.get("text") or {}
                        if tx.get("channel") == ANSWER_CHANNEL and tx.get("text"):
                            final_text = tx["text"]
            elif typ == "response.output_text.done":
                tx = ev.get("text")
                if tx:
                    final_text = tx
            elif typ == "response.done":
                done = True
            elif typ == "error":
                raise ChatError("RESPONSE_ERROR", json.dumps(ev)[:200])

        answer = (final_text or "".join(parts)).strip()
        if not answer:
            raise ChatError("EMPTY_ANSWER", "no answer text in grok ws stream")
        if _ERR_SIG.search(answer):
            # An error string is not supply (Law 2/3). Auth-shaped -> expired, else upstream error.
            if re.search(r"(sign ?in|log ?in|unauthenticated|unauthorized|expired|session.moved)",
                         answer, re.I):
                raise SessionExpired("AUTH", answer[:160])
            raise ChatError("UPSTREAM_ERROR", answer[:200])

        return {
            "text": answer,
            "label": "grok-ws-replay",
            "status": 200,
            "raw": {"model": use_model, "conversation_id": conv,
                    "ms": int((time.time() - t0) * 1000)},
        }


if __name__ == "__main__":
    import pathlib as _pl
    seat = _pl.Path(r"D:\omniroute-monetizer\state\secrets\session_grok_ws.json")
    c = GrokWsClient(secret=seat)
    out = c.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
    print("LABEL:", out["label"])
    print("STATUS:", out["status"])
    print("TEXT:", out["text"])
    print("MS:", out["raw"]["ms"])
