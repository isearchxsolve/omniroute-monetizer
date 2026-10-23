#!/usr/bin/env python3
"""Pure-python WEBSOCKET replay for captured chat seats (transport: "websocket").

The Chrome-gap doctrine in action: a WEBSOCKET capture outcome names the transport to
build, never a dead end. Chrome chats over a websocket -- iFlytek SparkDesk produced
0 HTTP posts / 143 ws frames, Meta AI 11 posts / 39 frames -- so a websocket capture must
be re-sendable over a websocket, exactly as universal_replay re-sends an HTTP exchange.

Same contract, same rules as the HTTP adapter:

  * the capture (capture_sessions_cdp.py) records the genuine exchange: the handshake url,
    the headers Chrome sent, and every SENT frame in order (`recorded_ws`);
  * at call time the sentinel is string-replaced inside the recorded frames (or binary
    Protobuf varint-patched for binary frames) -- the protocol is never rebuilt from
    scratch, so every field the site's own client sends stays in;
  * received frames are pumped and assembled, then handed to the SAME extraction pipeline
    (_extract_response) and the same strict numeric verdict as the HTTP path.

Errors mirror universal_replay's semantics (ChatError with .raw/.status) so replay_check's
keyword-search unlock and classify() work unchanged. Cookie rotation on the ws handshake is
not absorbed (websocket-client does not expose response headers portably) -- noted honestly;
ws session lifetimes are bounded by that.
"""
import base64
import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Union

import websocket                      # websocket-client -- already the CDP transport's lib

from veoaifree_chat_client import ChatError          # noqa: E402  (canonical exception)
from universal_replay import (                       # noqa: E402  (extraction + protobuf pipeline)
    UniversalSessionClient,
    substitute_protobuf_bytes,
    extract_protobuf_strings,
)

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


def _parse_ws_proxy_kwargs(proxy_url: Optional[str]) -> Dict[str, Any]:
    """Convert an HTTP/SOCKS5 proxy URL into websocket.create_connection kwargs."""
    if not proxy_url:
        return {}
    parsed = urllib.parse.urlparse(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
    if not parsed.hostname or not parsed.port:
        return {}
    scheme = (parsed.scheme or "http").lower()
    if scheme.startswith("socks5"):
        ptype = "socks5h" if "socks5h" in scheme else "socks5"
    elif scheme.startswith("socks4"):
        ptype = "socks4"
    else:
        ptype = "http"
    kw: Dict[str, Any] = {
        "http_proxy_host": parsed.hostname,
        "http_proxy_port": parsed.port,
        "proxy_type": ptype,
    }
    if parsed.username:
        kw["http_proxy_auth"] = (
            urllib.parse.unquote(parsed.username),
            urllib.parse.unquote(parsed.password or ""),
        )
    return kw


class WebSocketSessionClient:
    """Same .chat() contract as UniversalSessionClient, over the recorded websocket."""

    def __init__(self, path=None, secret=None):
        # `secret=` is the pool's constructor contract (PooledSession.client passes it);
        # `path=` kept for the replay_check/direct callers.
        import pathlib
        self.path = pathlib.Path(secret or path)
        self.raw: Dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        self.rec: Dict[str, Any] = self.raw.get("recorded_ws") or {}
        if not self.rec.get("url"):
            raise ChatError("NO_WS_URL", "capture has no recorded_ws.url to replay")
        self.url: str = self.rec["url"]
        self.sent_frames: list = list(self.rec.get("sent_frames") or [])
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

        try:
            from multistep_replay import resolve_egress_proxy
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
            from multistep_replay import resolve_egress_proxy
        self.proxy: Optional[str] = resolve_egress_proxy(self.raw, self.raw.get("host"))

    # -- sentinel injection: text frames + binary Protobuf frames (Point 5) ----------------
    def _inject(self, new_prompt: str) -> List[Union[str, bytes]]:
        pairs = list(zip(_sentinel_forms(self.sentinel), _sentinel_forms(new_prompt)))
        out: List[Union[str, bytes]] = []
        hits = 0
        for raw_frame in self.sent_frames:
            # Binary frame representation: {"type": "binary", "data_b64": "..."} or "base64:..."
            if isinstance(raw_frame, dict) and raw_frame.get("data_b64"):
                raw_bytes = base64.b64decode(raw_frame["data_b64"])
                patched_b, h = substitute_protobuf_bytes(
                    raw_bytes, new_prompt, extra_sentinels=[self.sentinel]
                )
                hits += h
                out.append(patched_b)
                continue
            if isinstance(raw_frame, str) and raw_frame.startswith("base64:"):
                raw_bytes = base64.b64decode(raw_frame[7:])
                patched_b, h = substitute_protobuf_bytes(
                    raw_bytes, new_prompt, extra_sentinels=[self.sentinel]
                )
                hits += h
                out.append(patched_b)
                continue

            frame = str(raw_frame)
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

    @staticmethod
    def _ws_send(ws, frame: Union[str, bytes]) -> None:
        if isinstance(frame, bytes):
            ws.send(frame, opcode=websocket.ABNF.OPCODE_BINARY)
        else:
            ws.send(frame)

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

        ws_kwargs: Dict[str, Any] = {
            "timeout": self.timeout,
            "header": self.headers,
            "suppress_origin": True,
            "max_size": 16 * 1024 * 1024,
        }
        ws_kwargs.update(_parse_ws_proxy_kwargs(getattr(self, "proxy", None)))

        try:
            ws = websocket.create_connection(self.url, **ws_kwargs)
        except websocket.WebSocketBadStatusException as e:
            # 401/403 at the handshake: replay_check's classify() reads these as AUTH.
            raise ChatError("HTTP_ERROR", f"ws handshake rejected: {e}") from e
        except Exception as e:                       # transport failure is data, not a crash
            raise ChatError("HTTP_ERROR", str(e)) from e

        payloads: list = []
        append_texts: list = []
        acked_connected = False
        last_text_at = time.monotonic()
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
            grok = host.endswith("grok.com")
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
                send_frames = [f for f in unique_frames if isinstance(f, str) and '"event":"send"' in f]
                if not send_frames:
                    raise ChatError("SENTINEL_NOT_FOUND",
                                    "copilot replay: no send frame in the recorded sequence")
                unique_frames = COPILOT_HANDSHAKE_FRAMES + [
                    _re.sub(r'"conversationId":"[A-Za-z0-9]+"',
                            f'"conversationId":"{fresh}"', f) for f in send_frames]
            if grok:
                # Grok's protocol (measured in the recorded frames, 2026-09-01): the FIRST
                # frame is a session.create whose event_id is client-minted and whose
                # session_id the SERVER assigns; the response.create frame then references
                # that session_id. Replaying a stale session_id addresses a session the
                # server has torn down: it answers {"event":{"type":"error"}} and no reply
                # stream ever opens (exact run-1 verdict). Chrome's own client mints both
                # per message, so the replay does the same: send session.create with a
                # fresh event_id, read the server-assigned session_id from its ack, rewrite
                # every subsequent frame with it, then send them.
                import json as _json
                import re as _re
                import uuid as _uuid
                create_frame = next((f for f in unique_frames if isinstance(f, str) and '"session.create"' in f), None)
                send_frames = [f for f in unique_frames if isinstance(f, str) and '"response.create"' in f]
                if not send_frames:
                    raise ChatError("SENTINEL_NOT_FOUND",
                                    "grok replay: no response.create frame in the recorded sequence")
                sid = None
                if create_frame:
                    create_frame = _re.sub(r'"event_id":"evt_init_[^"]+"',
                                           f'"event_id":"evt_init_{_uuid.uuid4()}"', create_frame)
                    self._ws_send(ws, create_frame)
                    deadline_ack = time.monotonic() + 15.0
                    while time.monotonic() < deadline_ack and not sid:
                        try:
                            ws.settimeout(1.0)
                            ack = ws.recv()
                        except websocket.WebSocketTimeoutException:
                            continue
                        except (websocket.WebSocketConnectionClosedException, ConnectionError):
                            break
                        if isinstance(ack, bytes):
                            ack = ack.decode("utf-8", "replace")
                        if not ack:
                            continue
                        payloads.append(ack)
                        last_text_at = time.monotonic()
                        try:
                            ad = _json.loads(ack)
                        except ValueError:
                            continue
                        ev = ad.get("event") if isinstance(ad.get("event"), dict) else {}
                        sid = (ad.get("session_id") or ev.get("session_id")
                               or (ev.get("session") or {}).get("session_id"))
                    if not sid:
                        raise ChatError("HTTP_ERROR",
                                        "grok replay: session.create produced no session_id "
                                        "(server error or protocol change)")
                rewritten = [_re.sub(r'"session_id":"[A-Za-z0-9-]+"',
                                     f'"session_id":"{sid}"', f) for f in send_frames]
                if '"presence.update"' in " ".join(str(x) for x in unique_frames):
                    presence = next(f for f in unique_frames if isinstance(f, str) and '"presence.update"' in f)
                    rewritten.append(_re.sub(r'"session_id":"[A-Za-z0-9-]+"',
                                             f'"session_id":"{sid}"', presence))
                for frame in rewritten:
                    self._ws_send(ws, frame)
            else:
                for frame in unique_frames:
                    self._ws_send(ws, frame)
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
                    proto_strs = extract_protobuf_strings(msg)
                    if proto_strs:
                        for ps in proto_strs:
                            if ps.strip() and ps.strip() != new_prompt.strip():
                                append_texts.append(ps)
                        msg = "\n".join(proto_strs)
                    else:
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
                        # Grok reply shape (PINNED from live frames 2026-09-01, see
                        # state/replay_raw/ws_grok.com_*.txt): the answer arrives as
                        # {"event":{"type":"response.chunk","chunk":{"text":{"text":"58",
                        # "channel":"CHANNEL_ASSISTANT_RESPONSE"}}}}. The server also streams
                        # UI noise through the same chunk shape
                        # (CHANNEL_ASSISTANT_NOTETAKER_HEADER: "Thinking about your request")
                        # -- only the RESPONSE channel is the model's words. Terminators:
                        # response.done / response.persisted.
                        ev = d.get("event")
                        if isinstance(ev, dict):
                            etype = str(ev.get("type") or "")
                            if etype == "response.chunk":
                                chunk = ev.get("chunk") or {}
                                txt = chunk.get("text") or {}
                                if (txt.get("channel") == "CHANNEL_ASSISTANT_RESPONSE"
                                        and txt.get("text")):
                                    append_texts.append(str(txt["text"]))
                            elif etype in ("response.done", "response.persisted") and append_texts:
                                break
        finally:
            try:
                ws.close()
            except Exception:
                pass

        joined = "\n".join(payloads)
        if not joined:
            raise ChatError("HTTP_ERROR", "ws replay received no frames before its deadline")

        # Forensics: keep the received frames so a reply-shape gap is diagnosed from the
        # actual server events, never guessed (same discipline as state/replay_raw for HTTP).
        try:
            import pathlib as _pl
            _raw_dir = _pl.Path(__file__).resolve().parents[2] / "state" / "replay_raw"
            _raw_dir.mkdir(parents=True, exist_ok=True)
            (_raw_dir / f"ws_{self.raw.get('host', 'unknown')}_{int(time.time())}.txt").write_text(
                joined, encoding="utf-8")
        except Exception:
            pass

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