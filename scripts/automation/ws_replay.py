#!/usr/bin/env python3
"""Pure-python WEBSOCKET replay for captured chat seats (transport: "websocket").

The Chrome-gap doctrine in action: a WEBSOCKET capture outcome names the transport to
build, never a dead end. Chrome chats over a websocket -- iFlytek SparkDesk produced
0 HTTP posts / 143 ws frames, Meta AI 11 posts / 39 frames -- so a websocket capture must
be re-sendable over a websocket, exactly as universal_replay re-sends an HTTP exchange.

Same contract, same rules as the HTTP adapter:

  * the capture (capture_sessions_cdp.py) records the genuine exchange: the handshake url,
    the headers Chrome sent, and every SENT frame in order (`recorded_ws`);
  * at call time the sentinel is string-replaced inside the recorded frames -- the protocol
    is never rebuilt from scratch, so every field the site's own client sends stays in;
  * received frames are pumped and assembled, then handed to the SAME extraction pipeline
    (_extract_response) and the same strict numeric verdict as the HTTP path.

Errors mirror universal_replay's semantics (ChatError with .raw/.status) so replay_check's
keyword-search unlock and classify() work unchanged. Cookie rotation on the ws handshake is
not absorbed (websocket-client does not expose response headers portably) -- noted honestly;
ws session lifetimes are bounded by that.
"""
import json
import time
import urllib.parse
from typing import Any, Dict, Optional

import websocket                      # websocket-client -- already the CDP transport's lib

from veoaifree_chat_client import ChatError          # noqa: E402  (canonical exception)
from universal_replay import UniversalSessionClient  # noqa: E402  (extraction pipeline)

DEFAULT_SENTINEL = "Reply exactly one word: Omni."

# CURRENT Copilot handshake frames, captured byte-for-byte off the live page with a two-way
# CDP websocket sniff (2026-08-30). The frames recorded in the session file go stale: the
# server answers a replayed old setOptions with {"event":"error","errorCode":"invalid-event"}.
# These are static client-version config frames (feature flags), not per-message state, so
# embedding today's bytes is the faithful reproduction. If Copilot ships a new client, a
# fresh sniff refreshes them.
COPILOT_HANDSHAKE_FRAMES = [
    '{"event":"setOptions","supportedFeatures":["partial-generated-images","composer-prefill-conversation-action","composer-send-conversation-action-v2","side-by-side-comparison","session-duration-nudge","compose-email-html"],"supportedCards":["weather","local","image","sports","video","healthcareEntity","healthcareInfo","healthRecordsConnectNewProvider","healthRecordsUpdate","suggestHealth","chart","ads","safetyHelpline","quiz","finance","recipe","personalArtifacts","flashcard","navigation","person","powerPointCreator","consentV2","composeEmail","createCalendarEvent","modifyCalendarEvent","deleteCalendarEvent","practiceTest","tapToReveal"],"supportedUIComponents":{"Badge":"1.2","Basic":"1.2","Box":"1.2","Button":"1.2","Card":"1.2","Caption":"1.2","Chart":"1.2","Checkbox":"1.2","Col":"1.2","DatePicker":"1.3","Divider":"1.2","Form":"1.2","Icon":"1.2","Image":"1.2","Label":"1.2","ListView":"1.2","ListViewItem":"1.2","Map":"1.3","Markdown":"1.2","Pressable":"1.3","RadioGroup":"1.3","Row":"1.2","Select":"1.3","Spacer":"1.2","Table":"1.3","Table.Cell":"1.3","Table.Row":"1.3","Text":"1.2","Textarea":"1.3","Title":"1.2","Transition":"1.2"},"ads":{"supportedTypes":["text","product","multimedia","tourActivity","propertyPromotion"]},"supportedActions":[]}',
    '{"event":"reportLocalConsents","grantedConsents":[]}',
]

# websocket-client generates its own handshake (Host, Upgrade, Connection, Sec-WebSocket-*),
# and a stale recorded value there would corrupt the handshake. Everything else the site's
# own client sent -- User-Agent, Origin, Cookie -- is replayed verbatim.
_SKIP_HEADERS = ("host", "upgrade", "connection", "content-length", "sec-websocket-key",
                 "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol")


def _sentinel_forms(s: str) -> list[str]:
    return [s, urllib.parse.quote_plus(s), urllib.parse.quote(s), json.dumps(s)[1:-1]]


class WebSocketSessionClient:
    """Same .chat() contract as UniversalSessionClient, over the recorded websocket."""

    def __init__(self, path):
        import pathlib
        self.path = pathlib.Path(path)
        self.raw: Dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        self.rec: Dict[str, Any] = self.raw.get("recorded_ws") or {}
        if not self.rec.get("url"):
            raise ChatError("NO_WS_URL", "capture has no recorded_ws.url to replay")
        self.url: str = self.rec["url"]
        self.sent_frames: list = [str(f) for f in (self.rec.get("sent_frames") or [])]
        self.sentinel: str = self.raw.get("sentinel") or DEFAULT_SENTINEL
        self.cookie_header: str = (self.raw.get("cookie_header")
                                   or self.rec.get("cookie_header") or "")
        self.timeout: float = float(self.rec.get("timeoutS") or 45.0)
        self.quiet_s: float = float(self.rec.get("quietS") or 6.0)
        self.headers: list = []
        for k, v in (self.rec.get("request_headers") or {}).items():
            if not isinstance(v, str) or k.lower() in _SKIP_HEADERS:
                continue
            self.headers.append(f"{k}: {v}")
        if self.cookie_header:
            self.headers.append(f"Cookie: {self.cookie_header}")

    # -- sentinel injection: same one-string-replacement rule as the HTTP path ------------
    def _inject(self, new_prompt: str) -> list[str]:
        pairs = list(zip(_sentinel_forms(self.sentinel), _sentinel_forms(new_prompt)))
        out, hits = [], 0
        for frame in self.sent_frames:
            n = 0
            for old, new in pairs:
                if old and old in frame:
                    n += frame.count(old)
                    frame = frame.replace(old, new)
            hits += n
            out.append(frame)
        if not hits:
            raise ChatError(
                "SENTINEL_NOT_FOUND",
                f"could not inject the prompt into the recorded ws frames for "
                f"{self.raw.get('host')} -- no sentinel form matched, so the replay would "
                f"re-send the captured probe instead of the caller's prompt.")
        return out

    def chat(self, messages: list, model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        new_prompt = str(messages[-1].get("content") or "")
        frames = self._inject(new_prompt)

        # The capture can hold retry loops (Copilot recorded the same 3-frame group 23 times
        # because its client re-submits on every socket flap). Re-sending 23 duplicate groups
        # hammers the seat and buries the reply under duplicate streams. First occurrence of
        # each unique frame, in first-seen order, is the logical protocol sequence.
        seen: set = set()
        unique_frames = [f for f in frames if not (f in seen or seen.add(f))]

        try:
            ws = websocket.create_connection(self.url, timeout=self.timeout,
                                             header=self.headers, suppress_origin=True,
                                             max_size=16 * 1024 * 1024)
        except websocket.WebSocketBadStatusException as e:
            # 401/403 at the handshake: replay_check's classify() reads these as AUTH.
            raise ChatError("HTTP_ERROR", f"ws handshake rejected: {e}") from e
        except Exception as e:                       # transport failure is data, not a crash
            raise ChatError("HTTP_ERROR", str(e)) from e

        payloads: list = []
        append_texts: list = []
        acked_connected = False
        try:
            host = urllib.parse.urlparse(self.url).hostname or ""
            # Copilot handshake (two-way CDP sniff of the live page, 2026-08-30): after the send
            # the server replies {"event":"connected"} and STALLS until the client answers
            # {"type":"sequenceAck","sequenceId":0}; only then do the reply events stream
            # (received -> startMessage -> appendText{"text":...} -> partCompleted -> done).
            # The connected frame arrives AFTER the send in Chrome's own flow, so the ack is
            # answered inside the pump loop, not before sending. Keyed to the host: a stray
            # sequenceAck on a server that never asked for it is a protocol violation we must
            # not introduce for the other ws seats.
            copilot = host.endswith("copilot.microsoft.com")
            if copilot:
                # The send frame carries a conversationId the CLIENT mints per new chat
                # (Chrome's own page created a fresh one per message -- two-way sniff
                # 2026-08-30). Re-playing yesterday's id addresses a conversation the server
                # no longer knows: connected is answered but the message is dropped. Mint a
                # fresh one, exactly as the browser does. The recorded handshake frames also
                # go stale (the server answers a replayed old setOptions with
                # {"event":"error","errorCode":"invalid-event"}), so the current client's
                # bytes from the sniff replace them; only the send frame comes from the file.
                import re as _re
                import secrets as _secrets
                fresh = "".join(_secrets.choice(
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
                    for _ in range(20))
                send_frames = [f for f in unique_frames if '"event":"send"' in f]
                if not send_frames:
                    raise ChatError("SENTINEL_NOT_FOUND",
                                    "copilot replay: no send frame in the recorded sequence")
                unique_frames = COPILOT_HANDSHAKE_FRAMES + [
                    _re.sub(r'"conversationId":"[A-Za-z0-9]+"',
                            f'"conversationId":"{fresh}"', f) for f in send_frames]
            for frame in unique_frames:
                ws.send(frame)
            deadline = time.monotonic() + self.timeout
            last_text_at = time.monotonic()
            while time.monotonic() < deadline:
                try:
                    ws.settimeout(1.0)
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    if payloads and time.monotonic() - last_text_at >= self.quiet_s:
                        break                        # answer complete; do not burn the window
                    continue
                except (websocket.WebSocketConnectionClosedException, ConnectionError):
                    break                            # server closed: we keep what we got
                if isinstance(msg, bytes):
                    try:
                        msg = msg.decode("utf-8", "replace")
                    except Exception:
                        continue
                if msg:
                    payloads.append(msg)
                    last_text_at = time.monotonic()
                    if copilot and not acked_connected and '"connected"' in msg:
                        ws.send('{"type":"sequenceAck","sequenceId":0}')
                        acked_connected = True
                        continue
                    # Event-stream reply assembly (Copilot shape): the model text arrives as
                    # appendText events; done terminates the message.
                    try:
                        d = json.loads(msg)
                    except ValueError:
                        d = None
                    if isinstance(d, dict):
                        if d.get("event") == "appendText" and d.get("text") is not None:
                            append_texts.append(str(d.get("text") or ""))
                        if d.get("event") == "done" and append_texts:
                            break
        finally:
            try:
                ws.close()
            except Exception:
                pass

        joined = "\n".join(payloads)
        if not joined:
            raise ChatError("HTTP_ERROR", "ws replay received no frames before its deadline")

        # Event-assembled text first (exact model words, no protocol noise), then the generic
        # extraction pipeline over the raw frames as the fallback.
        final_event_text = "".join(append_texts).strip()
        if final_event_text:
            return {"text": final_event_text, "label": "ws-adapter+events",
                    "status": 200, "raw": joined}

        # Same extraction pipeline as the HTTP adapter: the received frames are JSON/protocol
        # text, and the parsers already know SSE, whole-body JSON, chunked text and echo
        # filtering. The no-tool envelope unwrap also applies (chat_pool_server's contract).
        ex = UniversalSessionClient.__new__(UniversalSessionClient)
        ex._last_prompt = new_prompt
        final_text, err = ex._extract_response(joined)
        # or-form, never the conditional: the helper returns None for any non-envelope,
        # and a plain answer ("58") must survive the call untouched.
        final_text = unwrap_no_tool_text(final_text) or final_text
        if not final_text:
            e = ChatError("UPSTREAM_ERROR", err or "ws reply assembled to nothing")
            e.raw = joined
            e.status = 200
            raise e
        return {"text": final_text, "label": "ws-adapter", "status": 200, "raw": joined}


# The canonical no-tool envelope helper lives in chat_pool_server (stdlib-only module, no
# import side effects); imported late so this file's docstring stays the primary import.
from chat_pool_server import unwrap_no_tool_text      # noqa: E402, F401  (used in chat())