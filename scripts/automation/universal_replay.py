import base64
import json
import os
import re
import struct
import sys
import time
import requests
from typing import Dict, Any, Optional, Tuple, List

# --- Browser-impersonation transport ---------------------------------------
# Servers fingerprint the client at the TLS Client Hello (JA3/JA4) and the
# HTTP/2 handshake (Akamai) BEFORE any HTTP header is read. Python `requests`
# negotiates with OpenSSL over HTTP/1.1, which is instantly recognisable as a
# script and is why replays get AUTH/WALL/UNPARSEABLE verdicts even with a
# valid session cookie. curl_cffi reproduces Chrome's exact TLS Client Hello
# and HTTP/2 frame signature while still sending OUR recorded HTTP headers
# byte-for-byte (Law 4). Fall back to requests when it is not installed.
try:
    import curl_cffi
    from curl_cffi.requests import exceptions as _cc_exc
    _HAVE_CURL_CFFI = True
    _TRANSPORT_EXC = (_cc_exc.RequestException, requests.exceptions.RequestException)
except ImportError:
    curl_cffi = None
    _HAVE_CURL_CFFI = False
    _TRANSPORT_EXC = (requests.exceptions.RequestException,)

# Which browser to impersonate. "chrome" always tracks the latest Chrome
# fingerprint in the installed curl_cffi. The network-level handshake is what
# matters; the HTTP headers are the recorded ones, so this is not per-site.
_IMPERSONATE = "chrome"

# CANONICAL exception classes. session_pool.py's full-pool fall-through catches the exact class
# objects defined in veoaifree_chat_client / veo_session_replay. This file used to define its own
# lookalike classes here -- so a 429 raised below escaped the pool's `except ChatError` and the
# load balancer stopped after the FIRST session instead of rotating across the whole pool
# (2026-08-27, worklog #1109). Import the canonical ones; never redefine them.
from veoaifree_chat_client import ChatError          # noqa: E402  (canonical exception)
from veo_session_replay import SessionExpired        # noqa: E402  (subclass of ChatError)


def make_session_client(path):
    """Route a session file to its transport. HTTP is the default; a capture whose exchange
    left over a websocket (recorded_ws / transport marker) goes to the ws adapter."""
    import pathlib
    try:
        payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return UniversalSessionClient(path)
    if payload.get("transport") == "websocket" or payload.get("recorded_ws"):
        from ws_replay import WebSocketSessionClient
        return WebSocketSessionClient(path)
    return UniversalSessionClient(path)

# The tool-contract no-tool envelope ({"tool": null, "text": ...}) is defined by
# chat_pool_server.tool_instruction and legitimately arrives AS the model's reply whenever a
# seat's recorded request carries the contract (e.g. Cohere's captured exchange answers every
# probe inside this envelope, so the assembled reply is our wire format, not the answer).
# One canonical implementation lives in chat_pool_server -- stdlib-only module, no import side
# effects, so importing it here is safe. (The :8190 shim has a private copy predating this.)
from chat_pool_server import unwrap_no_tool_text     # noqa: E402

# A prompt shorter than this is never used to detect an echo by containment: aymo.ai's real answer
# "Hi!" contains the prompt "hi", and dropping it as an echo emptied the extraction entirely.
_ECHO_MIN_PROMPT = 24

# Diagnostics below print raw provider bodies (line 753+). Under a Windows cp1252 pipe, a CJK
# body raised UnicodeEncodeError out of print(), which propagated up through chat() and was
# then misread by replay_check as the model's reply text -- corrupting the seat verdict for
# every Chinese-language provider. Never let a diagnostic print decide a verdict: replace
# un-encodable characters instead of raising.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (ValueError, OSError):
        pass


# Substitution ladder, module-level so multi-exchange captures substitute EVERY leg
# the same way the first leg was substituted (see _inject_prompt and the
# recorded_exchanges threading in chat()). The recorded sentinel contains no special
# characters, so it is still searched for literally -- only the replacement is escaped.
# Escape whenever the body carries JSON ANYWHERE, not just when the whole body is JSON:
# huggingface.co posts multipart/form-data whose parts contain JSON, so a whole-body
# check said "not JSON", the raw newlines went in unescaped and the inner JSON stopped
# parsing -- HTTP 500. Defaulting to escaped is the safe direction: on a genuinely
# plain body the only cost is a newline arriving as the two characters \n, where the
# other order corrupts the payload outright.
_PROMPT_PLACEHOLDERS = (
    "Reply exactly one word: Omni.",
    "Reply exactly one word: Omni",
    "Reply exactly one word : Omni.",
    "Reply exactly one word : Omni",
    "Hi",
    "Hello",
)


# ---------------------------------------------------------------------------
# Point 5: Binary Protobuf / gRPC-Web / Connect Frame Surgery
# ---------------------------------------------------------------------------

def _encode_varint(n: int) -> bytes:
    """Encode an unsigned integer as a Protobuf base-128 varint."""
    if n < 0:
        raise ValueError("varint must be non-negative")
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _decode_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Decode a Protobuf varint starting at `pos`. Returns (value, new_pos)."""
    result = 0
    shift = 0
    length = len(buf)
    while pos < length:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift >= 64:
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def _patch_protobuf_message(
    buf: bytes,
    old_bytes_list: List[bytes],
    new_bytes: bytes,
    depth: int = 0,
) -> Tuple[bytes, int]:
    """Recursively walk a Protobuf message, replace sentinel bytes inside any
    length-delimited string/submessage, and recompute all enclosing Wire Type 2
    varint lengths bottom-up. Returns (patched_bytes, replacement_count)."""
    if depth > 16 or not buf:
        return buf, 0
    pos = 0
    length = len(buf)
    out = bytearray()
    total_hits = 0

    try:
        while pos < length:
            tag_start = pos
            tag, pos = _decode_varint(buf, pos)
            field_num = tag >> 3
            wire_type = tag & 0x07
            if field_num <= 0:
                return buf, 0
            tag_bytes = buf[tag_start:pos]

            if wire_type == 0:  # Varint
                val_start = pos
                _, pos = _decode_varint(buf, pos)
                out.extend(tag_bytes)
                out.extend(buf[val_start:pos])
            elif wire_type == 1:  # 64-bit
                if pos + 8 > length:
                    return buf, 0
                out.extend(tag_bytes)
                out.extend(buf[pos:pos + 8])
                pos += 8
            elif wire_type == 5:  # 32-bit
                if pos + 4 > length:
                    return buf, 0
                out.extend(tag_bytes)
                out.extend(buf[pos:pos + 4])
                pos += 4
            elif wire_type == 2:  # Length-delimited (string, bytes, submessage)
                sub_len, pos = _decode_varint(buf, pos)
                if sub_len < 0 or pos + sub_len > length:
                    return buf, 0
                payload = buf[pos:pos + sub_len]
                pos += sub_len

                # Only inspect if a sentinel actually appears inside `payload`
                matched_sentinel = next((old_b for old_b in old_bytes_list if old_b and old_b in payload), None)
                if matched_sentinel is not None:
                    # 1. Try recursive submessage patching first (if payload is an embedded message)
                    sub_patched, sub_hits = _patch_protobuf_message(
                        payload, old_bytes_list, new_bytes, depth=depth + 1
                    )
                    if sub_hits > 0:
                        payload = sub_patched
                        total_hits += sub_hits
                    else:
                        # 2. Leaf string/bytes field: replace directly and recompute varint length
                        for old_b in old_bytes_list:
                            if old_b and old_b in payload:
                                cnt = payload.count(old_b)
                                payload = payload.replace(old_b, new_bytes)
                                total_hits += cnt
                                break
                out.extend(tag_bytes)
                out.extend(_encode_varint(len(payload)))
                out.extend(payload)
            else:
                # Unknown/deprecated wire type -> not a valid protobuf frame at this level
                return buf, 0
    except ValueError:
        return buf, 0

    if total_hits == 0:
        return buf, 0
    return bytes(out), total_hits


def _is_grpc_web_framed(buf: bytes) -> bool:
    """True when `buf` consists of one or more 5-byte gRPC-Web / Connect envelopes:
    [1-byte flag (0x00 or 0x01 or 0x80)][4-byte big-endian uint32 length][payload]."""
    if len(buf) < 5:
        return False
    pos = 0
    frames = 0
    while pos < len(buf):
        if pos + 5 > len(buf):
            return False
        flag = buf[pos]
        if flag not in (0x00, 0x01, 0x80):
            return False
        frame_len = struct.unpack(">I", buf[pos + 1:pos + 5])[0]
        if pos + 5 + frame_len > len(buf):
            return False
        pos += 5 + frame_len
        frames += 1
    return frames >= 1 and pos == len(buf)


def substitute_protobuf_bytes(
    raw_bytes: bytes,
    new_prompt: str,
    content_type: str = "",
    extra_sentinels: Optional[List[str]] = None,
) -> Tuple[bytes, int]:
    """Replace the sentinel prompt inside a binary Protobuf or gRPC-Web / Connect payload,
    dynamically recomputing all Protobuf varint length prefixes and 5-byte gRPC-Web
    big-endian frame headers. Returns (patched_bytes, hit_count)."""
    if not raw_bytes:
        return raw_bytes, 0

    sentinels = list(extra_sentinels or []) + list(_PROMPT_PLACEHOLDERS)
    # Only use short placeholders ("Hi", "Hello") in binary mode if no primary sentinel is present
    primary = [s.encode("utf-8") for s in sentinels if len(s) >= 8]
    fallback = [s.encode("utf-8") for s in sentinels if 0 < len(s) < 8]
    new_b = new_prompt.encode("utf-8")

    ct_low = (content_type or "").lower()

    # Case 1: Base64-encoded gRPC-Web-Text (`application/grpc-web-text`)
    if "grpc-web-text" in ct_low:
        try:
            decoded = base64.b64decode(raw_bytes)
            patched_dec, hits = substitute_protobuf_bytes(
                decoded, new_prompt, content_type="application/grpc-web+proto", extra_sentinels=extra_sentinels
            )
            if hits > 0:
                return base64.b64encode(patched_dec), hits
        except Exception:
            pass

    old_list = primary if any(p in raw_bytes for p in primary) else fallback
    if not any(p in raw_bytes for p in old_list):
        return raw_bytes, 0

    # Case 2: 5-byte gRPC-Web / Connect framed sequence
    if _is_grpc_web_framed(raw_bytes) or "grpc" in ct_low or "connect+proto" in ct_low:
        if _is_grpc_web_framed(raw_bytes):
            pos = 0
            out = bytearray()
            total_hits = 0
            while pos < len(raw_bytes):
                flag = raw_bytes[pos]
                frame_len = struct.unpack(">I", raw_bytes[pos + 1:pos + 5])[0]
                frame_payload = raw_bytes[pos + 5:pos + 5 + frame_len]
                pos += 5 + frame_len
                if flag == 0x00:  # Uncompressed data frame
                    patched_payload, h = _patch_protobuf_message(frame_payload, old_list, new_b)
                    total_hits += h
                    out.append(flag)
                    out.extend(struct.pack(">I", len(patched_payload)))
                    out.extend(patched_payload)
                else:
                    out.append(flag)
                    out.extend(struct.pack(">I", len(frame_payload)))
                    out.extend(frame_payload)
            if total_hits > 0:
                return bytes(out), total_hits

    # Case 3: Raw Protobuf wire payload
    patched, hits = _patch_protobuf_message(raw_bytes, old_list, new_b)
    if hits > 0:
        return patched, hits

    return raw_bytes, 0


def extract_protobuf_strings(raw_bytes: bytes, depth: int = 0) -> List[str]:
    """Recursively extract UTF-8 text strings from a binary Protobuf or gRPC-Web response."""
    if depth > 12 or not raw_bytes:
        return []

    # Unwrap 5-byte gRPC-Web frames if present
    if depth == 0 and _is_grpc_web_framed(raw_bytes):
        pos = 0
        strings: List[str] = []
        while pos < len(raw_bytes):
            flag = raw_bytes[pos]
            frame_len = struct.unpack(">I", raw_bytes[pos + 1:pos + 5])[0]
            frame_payload = raw_bytes[pos + 5:pos + 5 + frame_len]
            pos += 5 + frame_len
            if flag == 0x00:
                strings.extend(extract_protobuf_strings(frame_payload, depth=1))
        return strings

    pos = 0
    length = len(raw_bytes)
    found: List[str] = []
    try:
        while pos < length:
            tag, pos = _decode_varint(raw_bytes, pos)
            field_num = tag >> 3
            wire_type = tag & 0x07
            if field_num <= 0:
                return []
            if wire_type == 0:
                _, pos = _decode_varint(raw_bytes, pos)
            elif wire_type == 1:
                if pos + 8 > length:
                    return []
                pos += 8
            elif wire_type == 5:
                if pos + 4 > length:
                    return []
                pos += 4
            elif wire_type == 2:
                sub_len, pos = _decode_varint(raw_bytes, pos)
                if sub_len < 0 or pos + sub_len > length:
                    return []
                payload = raw_bytes[pos:pos + sub_len]
                pos += sub_len
                # Try parsing as nested message first
                nested = extract_protobuf_strings(payload, depth=depth + 1)
                if nested:
                    found.extend(nested)
                else:
                    try:
                        s = payload.decode("utf-8")
                        if s and all(c.isprintable() or c in "\r\n\t" for c in s):
                            found.append(s)
                    except UnicodeDecodeError:
                        pass
            else:
                return []
    except ValueError:
        return []
    return found


def substitute_prompt(body: str, new_prompt: str) -> str:
    """Swap the recorded probe prompt for the caller's prompt in one body string."""
    import urllib.parse
    body = body or ""
    stripped = body.lstrip()
    is_json = stripped[:1] in ("{", "[") or '{"' in body
    esc = json.dumps(new_prompt)[1:-1]
    repl = esc if is_json else new_prompt
    for ph in _PROMPT_PLACEHOLDERS:
        if ph in body:
            return body.replace(ph, repl)
        # A url-encoded body is almost always a form field CARRYING JSON (Google's `f.req`,
        # Next.js server actions), so the replacement is json-escaped before it is percent
        # encoded. On a genuinely plain form field this only means a newline arrives as the
        # two characters \n instead of a real newline -- wrong but harmless, where the other
        # order corrupts the payload outright.
        ph_url = urllib.parse.quote_plus(ph)
        if ph_url in body:
            return body.replace(ph_url, urllib.parse.quote_plus(esc))
        ph_url2 = urllib.parse.quote(ph)
        if ph_url2 in body:
            return body.replace(ph_url2, urllib.parse.quote(esc))
    return body


def _leg2_for(provider_key: str, raw: dict, new_prompt: str):
    """The second recorded exchange of a multi-exchange capture, sentinel-substituted.

    Returns None for single-exchange captures (classic replay path unchanged) and for
    providers whose follow-up is not exchange-driven. chatgpt.com is the current
    consumer: prepare (leg 1, replayed as the recorded exchange) mints the conduit
    token, conversation (leg 2) carries the actual message. v0.app records a small
    analytics pair followed by the real `/chat/api/chat` submit; the final leg is the
    one that must be replayed before polling for the assistant message."""
    seq = raw.get("recorded_exchanges") or []
    if provider_key == "chatgpt.com":
        if len(seq) < 2:
            return None
        leg2 = dict(seq[1])
        leg2["request_body"] = substitute_prompt(str(leg2.get("request_body") or ""), new_prompt)
        return leg2
    if provider_key == "v0.app":
        # Prefer the actual chat submit over the `/chat/api/send` telemetry legs.  A
        # few older captures have only two exchanges, so choose the last one as the
        # least surprising fallback and let v0_followup fail honestly if it is not a
        # chat submit.
        candidates = [e for e in seq if "/chat/api/chat" in str(e.get("url") or "")]
        if not candidates:
            candidates = seq[1:]
        if not candidates:
            return None
        leg2 = dict(candidates[-1])
        leg2["request_body"] = substitute_prompt(str(leg2.get("request_body") or ""), new_prompt)
        return leg2
    if len(seq) >= 2:
        leg2 = dict(seq[1])
        if isinstance(seq[0], dict) and seq[0].get("response_body"):
            leg2["prev_response_body"] = seq[0].get("response_body")
        leg2["request_body"] = substitute_prompt(str(leg2.get("request_body") or ""), new_prompt)
        return leg2
    return None


def _followup_legs_for(raw: dict, new_prompt: str) -> List[Dict[str, Any]]:
    """Return all follow-up legs (leg 2..N) from `recorded_exchanges`, sentinel-substituted."""
    seq = raw.get("recorded_exchanges") or []
    if len(seq) < 2:
        return []
    out: List[Dict[str, Any]] = []
    for idx in range(1, len(seq)):
        if not isinstance(seq[idx], dict):
            continue
        leg = dict(seq[idx])
        prev = seq[idx - 1]
        if isinstance(prev, dict) and prev.get("response_body"):
            leg["prev_response_body"] = prev.get("response_body")
        leg["request_body"] = substitute_prompt(str(leg.get("request_body") or ""), new_prompt)
        out.append(leg)
    return out


def _followup_http_status(error: str, fallback: int | None = None) -> int | None:
    """Extract a follow-up HTTP status from a multistep adapter error.

    Bootstrap requests commonly return HTTP 200 even when the subsequent submit or
    poll is rejected. Keeping the final-leg status attached lets replay_check classify
    the real failure (AUTH/RATE/WALL) instead of scoring the bootstrap as NO_ANSWER.
    """
    m = re.search(r"(?:V0_(?:CHAT_SUBMIT|POLL)|CHATGPT_LEG2|GENERIC_LEG\d+)_(\d{3})", str(error or ""))
    return int(m.group(1)) if m else fallback


# Common cookie names that carry a short-lived JWT mirrored in `Authorization: Bearer <jwt>`
_JWT_COOKIE_NAMES = (
    "__stytch_session_jwt",
    "stytch_session_jwt",
    "__session",
    "access_token",
    "auth_token",
    "id_token",
    "jwt",
    "token",
)


class UniversalSessionClient:
    """
    Universal HTTP Replay Adapter.
    Takes a session metadata JSON (which must contain a 'recorded_exchange' blueprint).
    Uses a fast LLM to inject the new prompt into the request payload,
    fires the HTTP request natively via requests, and uses an LLM to extract the response.
    """
    def __init__(self, secret):
        import pathlib
        # Kept so a rotated cookie can be written back to the file it came from. Without a path the
        # client still works; it just cannot persist rotation past its own process.
        self._src = None
        if isinstance(secret, pathlib.Path) or isinstance(secret, str):
            self._src = pathlib.Path(secret)
            with open(secret, "r", encoding="utf-8") as f:
                self.raw = json.load(f)
        else:
            self.raw = secret

        self.exchange = self._normalise_exchange(self.raw)
        if not self.exchange:
            raise ValueError(f"No recorded_exchange found for universal replay on {self.raw.get('host')}")
        self.url = self.exchange.get("url")
        self.method = self.exchange.get("method", "POST")

        # Filter out HTTP/2 pseudo-headers (like :authority, :path) which crash requests
        raw_headers = self.exchange.get("request_headers", {})
        self.headers = {k: v for k, v in raw_headers.items() if not k.startswith(":")}

        # The recorded content-length describes the RECORDED body. Substituting a prompt changes the
        # length, so keeping it means announcing the wrong size -- a truncated read or a 400 at the
        # provider. requests computes the right one from the body it is given.
        self.headers = {k: v for k, v in self.headers.items()
                        if k.lower() not in ("content-length", "content-md5")}

        self.base_body = self.exchange.get("request_body", "")
        self.base_body_b64 = self.exchange.get("request_body_b64", "")

        # Override cookies from the live session if available
        if "cookie_header" in self.raw:
            self.headers["cookie"] = self.raw["cookie_header"]
            self.headers["Cookie"] = self.raw["cookie_header"]

        # Add Origin header if missing (fixes HuggingFace CSRF protection)
        if not any(k.lower() == "origin" for k in self.headers.keys()):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.url)
            self.headers["origin"] = f"{parsed.scheme}://{parsed.netloc}"

        # Point 4: Resolve optional residential / SOCKS5 / HTTP egress proxy
        try:
            from multistep_replay import resolve_egress_proxy
        except ImportError:
            import pathlib as _pl
            sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import resolve_egress_proxy
        self.proxy: Optional[str] = resolve_egress_proxy(self.raw, self.raw.get("host"))

    # Three capture generations wrote three different shapes into state/secrets/. Reading only
    # the newest one meant an older file yielded base_body == "" -> a BODYLESS POST that often
    # still returns HTTP 200, i.e. a silent false green. Normalise on read instead.
    _URL_KEYS = ("url", "request_url")
    _METHOD_KEYS = ("method", "request_method")
    _BODY_KEYS = ("request_body", "post_data", "postData", "body", "payload")
    _HEADER_KEYS = ("request_headers", "headers", "request_header")

    @classmethod
    def _normalise_exchange(cls, raw: dict) -> Optional[Dict[str, Any]]:
        """Accept every capture schema and return the canonical one, or None."""
        cand = raw.get("recorded_exchange")

        # digen-style: {"recorded_job": {"exchanges": [...]}} -- pick the submit call, which is
        # the first exchange carrying a body (later ones are status polls).
        if not isinstance(cand, dict):
            job = raw.get("recorded_job")
            if isinstance(job, dict):
                exchanges = job.get("exchanges")
                if isinstance(exchanges, list):
                    bodied = [e for e in exchanges
                              if isinstance(e, dict) and cls._first(e, cls._BODY_KEYS)]
                    cand = bodied[0] if bodied else (exchanges[0] if exchanges else None)

        # some captures stored a bare list of exchanges at the top level
        if not isinstance(cand, dict):
            for key in ("exchanges", "recorded_exchanges", "captured_requests"):
                seq = raw.get(key)
                if isinstance(seq, list) and seq and isinstance(seq[0], dict):
                    bodied = [e for e in seq if cls._first(e, cls._BODY_KEYS)]
                    cand = bodied[0] if bodied else seq[0]
                    break

        if not isinstance(cand, dict):
            return None

        url = cls._first(cand, cls._URL_KEYS)
        if not url:
            return None
        headers = cls._first(cand, cls._HEADER_KEYS) or {}
        if not isinstance(headers, dict):
            headers = {}
        return {
            "url": url,
            "method": cls._first(cand, cls._METHOD_KEYS) or "POST",
            "request_headers": headers,
            "request_body": cls._first(cand, cls._BODY_KEYS) or "",
            "request_body_b64": cand.get("request_body_b64") or "",
        }

    @staticmethod
    def _first(d: dict, keys) -> Any:
        for k in keys:
            v = d.get(k)
            if v:
                return v
        return None

    def _inject_prompt(self, new_prompt: str) -> str:
        if not self.base_body:
            return ""
        return substitute_prompt(self.base_body, new_prompt)

    @staticmethod
    def _piece_from_obj(o) -> str:
        """Pull a text fragment from one parsed chunk across OpenAI/Anthropic/generic shapes."""
        if not isinstance(o, dict):
            return ""
        ch = o.get("choices")
        if isinstance(ch, list) and ch and isinstance(ch[0], dict):
            c0 = ch[0]
            d = c0.get("delta") or c0.get("message")
            if isinstance(d, dict):
                v = d.get("content") or d.get("text")
                if isinstance(v, str):
                    return v
            if isinstance(c0.get("text"), str):
                return c0["text"]
        d = o.get("delta")
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            v = d.get("text") or d.get("content")
            if isinstance(v, str):
                return v
        cb = o.get("content_block")
        if isinstance(cb, dict) and isinstance(cb.get("text"), str):
            return cb["text"]
        cont = o.get("content")
        if isinstance(cont, list):
            parts = [b.get("text", "") for b in cont if isinstance(b, dict)]
            if any(parts):
                return "".join(parts)
        # DuckChat's SSE protocol uses a top-level `message` string for each response delta (the
        # older endpoint returned the same field, and the current Responses-style envelope still
        # carries it on successful frames).  Treat it like the other visible text fields; metadata
        # objects are ignored because only strings are accepted here.
        for k in ("content", "text", "message", "answer", "token", "value", "output", "response", "completion"):
            v = o.get(k)
            if isinstance(v, str) and v:
                return v
        return ""


    @staticmethod
    def _error_from_obj(o) -> Optional[str]:
        if not isinstance(o, dict):
            return None
        if o.get("type") == "error":
            e = o.get("error") or o.get("message")
            return e if isinstance(e, str) else (json.dumps(e)[:200] if e else "stream error")
        e = o.get("error")
        if isinstance(e, str) and e:
            return e
        if isinstance(e, dict):
            return e.get("message") or json.dumps(e)[:200]
        return None

    def _is_echo(self, frag: str) -> bool:
        """True when a swept fragment is the prompt coming back, not generated text.

        Deliberately narrow, and the bounds were both learned the hard way:

          * NOT "anything that is a substring of the prompt" -- that destroys the answer, because a
            streamed reply arrives as tokens like "Ver" + "ified" and "Ver" is a substring of
            "Reply exactly one word: Verified".
          * `p in f` only counts for a LONG prompt. With prompt "hi", aymo.ai's real answer "Hi!"
            contains the prompt and was dropped as an echo, which emptied the extraction and made the
            whole SSE stream fall through to the raw fallback. A short prompt cannot be told apart
            from a short answer this way, so it is not tried.
        """
        p = (getattr(self, "_last_prompt", "") or "").strip().lower()
        f = (frag or "").strip().lower()
        if not p or not f:
            return False
        return f == p or (len(p) >= _ECHO_MIN_PROMPT and p in f)

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        head = text[:400].lstrip().lower()
        return (head.startswith(("<!doctype", "<html", "<?xml"))
                or "<meta " in head or "<head>" in head)

    @staticmethod
    def _strip_xssi(text: str) -> str:
        """Drop the anti-JSON-hijack prefix Google (and a few others) put in front of a JSON body."""
        t = (text or "").lstrip()
        for pref in (")]}'", "while(1);", "for(;;);"):
            if t.startswith(pref):
                return t[len(pref):].lstrip()
        return text

    @classmethod
    def _deep_strings(cls, node, depth: int = 0) -> list:
        """Every string in a nested list/dict, in order. Google's reply arrays are positional with
        no field names, so there is no key to look the answer up by."""
        if depth > 12:
            return []
        if isinstance(node, str):
            return [node]
        if isinstance(node, (list, tuple)):
            out = []
            for v in node:
                out.extend(cls._deep_strings(v, depth + 1))
            return out
        if isinstance(node, dict):
            out = []
            for v in node.values():
                out.extend(cls._deep_strings(v, depth + 1))
            return out
        return []

    @staticmethod
    def _google_error(text: str) -> Optional[str]:
        """Google signals a refusal in the SAME envelope it uses for answers, but with a null
        payload and a `BardErrorInfo` code instead:

            [["wrb.fr",null,null,null,null,[13,null,[["...BardErrorInfo",[1076]]]]]]

        Without this, the envelope parser finds no documents, falls through to the raw fallback and
        the refusal reads as an answer. Observed on gemini.google.com after two successful replays:
        the session is state-sensitive, so a refusal here means STOP, not retry.
        """
        if "BardErrorInfo" not in (text or ""):
            return None
        m = re.search(r"BardErrorInfo\"\s*,\s*\[\s*(\d+)", text)
        code = m.group(1) if m else "unknown"
        return (f"GOOGLE_REFUSED: BardErrorInfo {code} -- the session replied to earlier replays and "
                f"is now refusing. State-sensitive or rate-limited; do not retry.")

    @classmethod
    def _google_envelope(cls, text: str) -> str:
        """Unwrap Google's batchexecute body: `)]}'`, then alternating length lines and JSON
        payloads, each `[["wrb.fr",null,"<escaped json>"]]` whose third element is JSON *inside* a
        JSON string. Neither json.loads on the body nor a regex sweep for `"text":"..."` reaches it.

        Parsed with a streaming json decoder rather than a regex -- a regex over this escaping is
        unwritable in practice, and the framing is newline-aligned so raw_decode walks it cleanly.

        This is a RESPONSE envelope, not a per-provider request adapter: the same shape is served by
        every Google property (Gemini, Flow, AI Studio), so one generic handler is worth it.

        Answer path measured on gemini.google.com 2026-08-26 (see inspect_reply_shape.py): the reply
        lives under `[4][0]` of the inner document, and the streaming increments repeat it, so the
        LAST document holds the most complete text.
        """
        t = cls._strip_xssi(text)
        if "wrb.fr" not in t:
            return ""
        dec = json.JSONDecoder()
        docs = []
        i = 0
        while i < len(t):
            while i < len(t) and t[i] not in "[{":
                i += 1
            if i >= len(t):
                break
            try:
                obj, end = dec.raw_decode(t, i)
            except ValueError:
                i += 1
                continue
            docs.extend(cls._unwrap_wrb(obj))
            i = end
        if not docs:
            return ""
        # Later documents are fuller versions of the same reply, so search from the end.
        for doc in reversed(docs):
            body = doc[4] if isinstance(doc, list) and len(doc) > 4 else None
            best = ""
            for s in cls._deep_strings(body if body is not None else doc):
                if len(s) <= len(best):
                    continue
                if s.startswith(("http://", "https://", "data:")) or "_" in s[:4]:
                    continue                                   # c_/r_/rc_ ids and urls
                best = s
            if best:
                return best[:4000].strip()
        return ""

    @classmethod
    def _unwrap_wrb(cls, obj) -> list:
        out = []
        if isinstance(obj, list):
            for row in obj:
                if (isinstance(row, list) and len(row) >= 3
                        and row[0] == "wrb.fr" and isinstance(row[2], str)):
                    try:
                        out.append(json.loads(row[2]))
                    except ValueError:
                        pass
                else:
                    out.extend(cls._unwrap_wrb(row))
        return out

    @staticmethod
    def _accumulate(pieces) -> str:
        """Join stream pieces, handling both delta and CUMULATIVE streams.

        Providers split roughly in half on this. A delta stream sends "Ver" then "ified" and the
        pieces must be concatenated. A cumulative stream (www.perplexity.ai) sends the whole answer
        so far in every event, so plain concatenation returns "5858" for an answer of "58".

        A piece that extends everything seen so far SUPERSEDES it; a repeat of the accumulation is
        dropped; anything else is appended. The `len(acc) >= 2` guard on the repeat case keeps a
        genuine delta of one repeated character ("a" then "a" -> "aa") from being swallowed.
        """
        acc = ""
        for p in pieces:
            if not p:
                continue
            if acc and p.startswith(acc) and len(p) > len(acc):
                acc = p
            elif acc and p == acc and len(acc) >= 2:
                continue
            else:
                acc += p
        return acc

    def _extract_response(self, response_text: str):
        """Return (assembled_text, error_message). Universal across SSE and whole-body JSON."""
        text = self._strip_xssi((response_text or "").strip())

        # Checked before the generic paths: a Google body is JSON nested in a JSON string, so the
        # SSE and whole-body branches both miss it and the raw fallback used to hand back `)]}'`.
        gerr = self._google_error(response_text or "")
        if gerr:
            return "", gerr
        g = self._google_envelope(response_text or "")
        if g:
            return g, None

        # tRPC / React-Query numbered-line patch stream (Mistral Le Chat answers the POST itself in
        # this shape). The answer is assembled from JSON patches -- "5" then append "8" -> "58" --
        # so neither the SSE branch nor a regex sweep for a single "text" field reaches it. This is
        # a RESPONSE envelope handler, not a per-provider request adapter.
        try:
            from multistep_replay import looks_like_trpc_stream, mistral_patch_stream_parse
        except ImportError:
            import pathlib as _pl, sys as _sys
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import looks_like_trpc_stream, mistral_patch_stream_parse
        if looks_like_trpc_stream(text):
            assembled = mistral_patch_stream_parse(text)
            if assembled:
                return assembled, None

        def scan(objs):
            pieces, err = [], None
            for o in objs:
                p = self._piece_from_obj(o)
                if p and not self._is_echo(p):     # a replayed body often carries the user turn back
                    pieces.append(p)
                e = self._error_from_obj(o)
                if e:
                    err = e
            return self._accumulate(pieces).strip(), err

        # 1) SSE stream: one JSON per `data:` line
        if text.startswith(("data:", "event:")) or "\ndata:" in text:
            objs = []
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                frag = line[5:].strip()
                if frag in ("", "[DONE]"):
                    continue
                try:
                    objs.append(json.loads(frag))
                except Exception:
                    continue

            # DeepSeek JSON-patch stream: first object carries the initial fragment inside a
            # deeply nested structure; subsequent objects are {"o":"APPEND","v":" token"} patches.
            # The generic _piece_from_obj only extracts from the first match, so concatenate
            # all "v" values from APPEND ops to reconstruct the full response text.
            ds_pieces = []
            for o in objs:
                op = o.get("o")
                v = o.get("v")
                p = o.get("p", "")
                if op == "APPEND" and isinstance(v, str):
                    # Explicit APPEND patch: {"p":"...content","o":"APPEND","v":" token"}
                    ds_pieces.append(v)
                elif not op and isinstance(v, str) and not isinstance(v, (dict, list)):
                    # Bare patch with no "o" key: {"v":" cow"} -- DeepSeek drops the op key
                    # after the first APPEND when the target path is implicit.
                    # Skip session/status metadata objects that also have "v" as a list/dict.
                    if p == "" or "content" in p or "fragment" in p:
                        ds_pieces.append(v)
                elif isinstance(v, dict):
                    # First big object: dig for the initial content fragment
                    try:
                        frags = v.get("response", {}).get("fragments", [])
                        for fr in frags:
                            c = fr.get("content", "")
                            if c:
                                ds_pieces.insert(0, c)
                    except Exception:
                        pass
            ds_assembled = "".join(ds_pieces).strip()
            if ds_assembled:
                return ds_assembled, None

            assembled, err = scan(objs)
            if assembled:
                return assembled, None
            if err:
                return "", err


        # 2) whole-body JSON
        try:
            assembled, err = scan([json.loads(text)])
            if assembled:
                return assembled, None
            if err:
                return "", err
        except Exception:
            pass

        # 3) regex sweep for chunked "content"/"text"/"delta" fields.
        # The sweep covers the WHOLE body, and many providers echo the user turn back inside a
        # `content` field -- often twice, once as the message and once in the conversation record.
        # Unfiltered, that echo is concatenated in FRONT of the real answer: chat.mistral.ai scored
        # as answering "reply exactly one word: verifiedreply exactly one word: verifiedver", which
        # is the prompt twice plus three generated characters. Echo fragments are dropped so what
        # survives is what the model actually produced.
        frags = re.findall(r'"(?:content|text|answer|delta)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        frags = [f for f in frags if not self._is_echo(f)]
        if frags:
            joined = self._accumulate(frags).replace('\\n', '\n').replace('\\"', '"').strip()
            if joined:
                return joined, None

        # 4) Nothing structured matched. Handing the raw body back as the reply is how a dead route
        # reads as a live one: an HTML login wall, error page or marketing landing arrives as "the
        # model's answer", and anything scoring that text for a keyword can find it in the page's own
        # markup -- veoaifree.com scored an answer of `<!doctype html>`, and you.com's reply carried
        # `width=device-width, initial-scale=1` from a <meta> tag. A body we cannot parse is a
        # failure, not an answer. Short plain-text bodies are still allowed through, because some
        # providers genuinely answer in text/plain.
        if self._looks_like_html(text):
            return "", (f"UNPARSEABLE_HTML: provider returned an HTML page, not an API response "
                        f"({len(text)} bytes) -- this session does not answer over this endpoint")
        # A stream we failed to parse is the same false-supply hazard as an HTML page, just
        # structured: handing the raw SSE back means the caller receives `event: chunk\ndata: {...}`
        # as the assistant's words. Observed on aymo.ai once the echo filter had wrongly emptied the
        # parse -- the reply was 804 characters of protocol.
        if "data: {" in text or text.lstrip().startswith("event:"):
            return "", (f"UNPARSEABLE_STREAM: {len(text)} bytes of event-stream that no parser "
                        f"branch could assemble -- refusing to return the protocol as a reply")
        if len(text) > 4000:
            return "", (f"UNPARSEABLE: {len(text)} bytes in no recognised response shape -- refusing "
                        f"to pass a raw body off as a model reply")
        return text[:2000].strip(), None

    # Providers rotate session cookies as they are used: the reply carries Set-Cookie and a real
    # browser stores it. A replay that keeps re-sending the jar recorded at capture time therefore
    # decays on the provider's own schedule no matter what any keepalive service does, because the
    # jar on disk is a SNAPSHOT and nothing was writing back to it. That is the actual expiry path
    # for these sessions -- OmniRoute's OAuth refresh endpoint cannot touch them, they are not
    # OmniRoute connections. Absorb the rotation and persist it instead.
    def _absorb_cookies(self, resp) -> int:
        rotated: Dict[str, str] = {}
        resp_headers_merged: Dict[str, str] = {}
        for r in list(getattr(resp, "history", []) or []) + [resp]:
            for name, value in self._iter_set_cookies(r):
                if name:
                    rotated[name] = value if value is not None else ""
            rh = getattr(r, "headers", None)
            if rh and hasattr(rh, "items"):
                for hk, hv in rh.items():
                    if hk and hv:
                        resp_headers_merged[str(hk).lower()] = str(hv)

        current = self.headers.get("cookie") or self.headers.get("Cookie") or ""
        jar: Dict[str, str] = {}
        order: list = []
        for part in current.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, _, v = part.partition("=")
            k = k.strip()
            if k and k not in jar:
                order.append(k)
            jar[k] = v.strip()

        old_jar = dict(jar)
        changed = 0
        for k, v in rotated.items():
            if not v:                       # cleared by the provider -- honour the deletion
                if jar.pop(k, None) is not None:
                    order = [o for o in order if o != k]
                    changed += 1
                continue
            if jar.get(k) != v:
                if k not in jar:
                    order.append(k)
                jar[k] = v
                changed += 1

        # Point 1: Synchronize `Authorization: Bearer <jwt>` or `x-auth-token` when a backing
        # session JWT cookie (Stytch, Clerk, NextAuth) or response auth header rotates.
        new_auth_bearer: Optional[str] = None
        for k, v in rotated.items():
            if not v:
                continue
            old_val = old_jar.get(k)
            # If the existing Authorization header held the exact old value of this cookie, or
            # if this cookie is a recognized JWT session cookie and Authorization is Bearer:
            for hk, hv in list(self.headers.items()):
                if hk.lower() == "authorization" and isinstance(hv, str):
                    if old_val and old_val in hv:
                        self.headers[hk] = hv.replace(old_val, v)
                        new_auth_bearer = self.headers[hk]
                        changed += 1
                    elif k.lower() in _JWT_COOKIE_NAMES and hv.lower().startswith("bearer "):
                        candidate = f"{hv[:7]}{v}"
                        if candidate != hv:
                            self.headers[hk] = candidate
                            new_auth_bearer = candidate
                            changed += 1

        # Also check explicit response token refresh headers (`x-auth-token`, `x-session-token`)
        for hdr_tok_name in ("x-auth-token", "x-session-token", "x-access-token"):
            if hdr_tok_name in resp_headers_merged:
                fresh_tok = resp_headers_merged[hdr_tok_name]
                for hk in list(self.headers.keys()):
                    if hk.lower() == hdr_tok_name and self.headers[hk] != fresh_tok:
                        self.headers[hk] = fresh_tok
                        changed += 1

        if not changed:
            return 0

        merged = "; ".join(f"{k}={jar[k]}" for k in order if k in jar)
        self.headers["cookie"] = merged
        self.headers["Cookie"] = merged
        self._persist_cookies(merged, new_auth_bearer=new_auth_bearer)
        return changed

    def _persist_cookies(self, merged: str, new_auth_bearer: Optional[str] = None) -> None:
        """Write the rotated jar back so the NEXT process starts from the fresh one, not the capture.

        Atomic (tmp + os.replace): a half-written secrets file would take a live provider off the pool.
        Writes to cookie_header because __init__ gives that key precedence over request_headers.
        Never logs or returns the value.
        """
        if self._src is None:
            return
        try:
            disk = json.loads(self._src.read_text(encoding="utf-8"))
            disk["cookie_header"] = merged
            # Keep the embedded copy consistent so a different reader cannot see a stale jar.
            hdrs = (disk.get("recorded_exchange") or {}).get("request_headers")
            if isinstance(hdrs, dict):
                for k in list(hdrs):
                    if k.lower() == "cookie":
                        hdrs[k] = merged
                    elif new_auth_bearer and k.lower() == "authorization":
                        hdrs[k] = new_auth_bearer
            # Also synchronize multi-leg `recorded_exchanges` headers if present
            for ex in disk.get("recorded_exchanges") or []:
                if isinstance(ex, dict) and isinstance(ex.get("request_headers"), dict):
                    ex_hdrs = ex["request_headers"]
                    for k in list(ex_hdrs):
                        if k.lower() == "cookie":
                            ex_hdrs[k] = merged
                        elif new_auth_bearer and k.lower() == "authorization":
                            ex_hdrs[k] = new_auth_bearer
            disk["cookieRotatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            tmp = self._src.with_name(self._src.name + ".tmp")
            tmp.write_text(json.dumps(disk, indent=2), encoding="utf-8")
            os.replace(tmp, self._src)
        except Exception:
            pass   # a stale jar on disk is survivable; losing the answer we just got is not

    # --- Transport ---------------------------------------------------------
    @staticmethod
    def _iter_set_cookies(resp):
        """Yield (name, value) for every Set-Cookie on a response, across both
        transports. `requests` iterates Cookie objects; curl_cffi iterates bare
        names with the objects on `.jar`."""
        cookies = getattr(resp, "cookies", None)
        if not cookies:
            return
        # curl_cffi: names on the wrapper, Cookie objects on .jar
        jar = getattr(cookies, "jar", None)
        if jar is not None:
            for c in jar:
                yield (getattr(c, "name", None), getattr(c, "value", None))
            return
        # requests: Cookie objects directly
        for c in cookies:
            if hasattr(c, "name"):
                yield (c.name, getattr(c, "value", None))

    def _fire(self, method: str, url: str, headers: Dict[str, str], body: Optional[bytes], timeout: float):
        """Send one request through the best available transport.

        Prefers curl_cffi browser impersonation (real Chrome TLS + HTTP/2
        fingerprint) so the server cannot tell this is a script. Falls back to
        plain requests when curl_cffi is unavailable. Returns a response object
        exposing .status_code/.ok/.text/.cookies/.history/.raise_for_status().
        """
        if _HAVE_CURL_CFFI:
            kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": timeout,
                "impersonate": _IMPERSONATE,
                # We replay the RECORDED headers byte-for-byte; do not let
                # curl_cffi inject its own default browser headers on top.
                "default_headers": False,
                "allow_redirects": True,
            }
            if body:
                kwargs["content"] = body
            if getattr(self, "proxy", None):
                kwargs["proxy"] = self.proxy
            return curl_cffi.request(method, url, **kwargs)

        kwargs = {"headers": headers, "timeout": timeout}
        if body:
            kwargs["data"] = body
        if getattr(self, "proxy", None):
            kwargs["proxies"] = {"http": self.proxy, "https": self.proxy}
        return requests.request(method, url, **kwargs)

    def chat(self, messages: list, model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")

        new_prompt = messages[-1]["content"]
        # Recorded so _extract_response can tell a generated reply from the prompt echoed back.
        self._last_prompt = str(new_prompt)

        content_type = next(
            (str(v) for k, v in self.headers.items() if k.lower() == "content-type"),
            "",
        )
        is_binary_proto = (
            bool(getattr(self, "base_body_b64", ""))
            or any(tok in content_type.lower() for tok in ("protobuf", "grpc-web", "connect+proto", "octet-stream"))
        )

        # Point 5: Binary Protobuf / gRPC-Web / Connect Frame path
        proto_body_bytes: Optional[bytes] = None
        if is_binary_proto:
            raw_proto = (
                base64.b64decode(self.base_body_b64)
                if getattr(self, "base_body_b64", "")
                else (self.base_body.encode("latin1") if isinstance(self.base_body, str) else bytes(self.base_body or b""))
            )
            patched_proto, proto_hits = substitute_protobuf_bytes(raw_proto, new_prompt, content_type=content_type)
            if proto_hits > 0:
                proto_body_bytes = patched_proto

        # 1. Inject prompt using string substitution ladder
        new_body_str = self._inject_prompt(new_prompt)

        # 1a. Pre-flight mutations: refresh client-generated identifiers that the server
        # rejects if reused (e.g. Mistral's messageId UUID -> 409 on reuse) and dynamic
        # anti-replay headers (X-Timestamp, X-Nonce, X-Request-Id, ChatGLM X-Sign).
        try:
            from multistep_replay import apply_preflight, apply_dynamic_headers
        except ImportError:
            import pathlib as _pl, sys as _sys
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import apply_preflight, apply_dynamic_headers
        import urllib.parse as _up
        netloc = _up.urlsplit(self.url).netloc
        new_body_str = apply_preflight(netloc, new_body_str)
        self.headers = apply_dynamic_headers(netloc, self.headers, new_body_str)

        # Monica: deterministic send-time surgery, BEFORE the sentinel check. The LLM
        # injector cannot be trusted for this shape and apply_preflight's unrelated body
        # change masks its failure (the check below passes while the recorded prompt is
        # still in the payload -- the server then answers the ORIGINAL prompt, which is
        # exactly how "Omni." came back for a holy-cow probe). Parsed-JSON surgery:
        #   - every question item's summary AND data.content get the caller's prompt;
        #   - every task:/msg: uuid is rotated COHERENTLY (one fresh uuid per old value)
        #     so item_id/parent_item_id/pre_parent_item_id links survive -- the old
        #     regex minted a different uuid per occurrence and severed the tree.
        if "api.monica.im" in (self.url or "") and self.base_body:
            import json as _mjson
            import re as _mre
            import uuid as _muuid
            _mid = _mre.compile(r"^(task|msg):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
            try:
                _mb = _mjson.loads(new_body_str)
                _idmap: Dict[str, str] = {}

                def _rot(o):
                    if isinstance(o, dict):
                        return {k: _rot(v) for k, v in o.items()}
                    if isinstance(o, list):
                        return [_rot(v) for v in o]
                    if isinstance(o, str) and _mid.match(o):
                        if o not in _idmap:
                            _idmap[o] = f"{o.split(':', 1)[0]}:{_muuid.uuid4()}"
                        return _idmap[o]
                    return o

                _mb = _rot(_mb)
                _items = (( _mb.get("data") or {} ).get("items") or []) if isinstance(_mb, dict) else []
                for _it in _items:
                    if isinstance(_it, dict) and _it.get("item_type") == "question":
                        _it["summary"] = new_prompt
                        if isinstance(_it.get("data"), dict):
                            _it["data"]["content"] = new_prompt
                if _idmap or _items:
                    new_body_str = _mjson.dumps(_mb)
            except ValueError:
                pass  # body was not JSON after all -- fall through to the generic path


        # A recorded POST with no body is a broken capture, not a live session. Firing it
        # anyway often returns HTTP 200 from an error/landing page and reads as success.
        if str(self.method).upper() in ("POST", "PUT", "PATCH") and not new_body_str and proto_body_bytes is None:
            raise ChatError(
                "EMPTY_BODY",
                f"capture for {self.raw.get('host')} has no replayable request "
                f"body (schema keys present: {sorted(self.raw.keys())}). Re-capture it; "
                f"do not treat a 200 from a bodyless POST as a working session."
            )

        # 1b. The sentinel must actually have been replaced, or we would send the recorded
        # probe prompt and log the model's answer to *that* as if it answered the caller.
        # In multi-leg captures (e.g. ChatGPT prepare -> conversation, or generic 2-leg flows),
        # Leg 1 may be a bootstrap request whose body does not contain the prompt while Leg 2 does.
        import urllib.parse
        followup_legs = _followup_legs_for(self.raw, new_prompt)
        prompt_in_followup = any(
            new_prompt in str(lg.get("request_body") or "")
            or json.dumps(new_prompt)[1:-1] in str(lg.get("request_body") or "")
            for lg in followup_legs
        )
        prompt_found = (
            proto_body_bytes is not None or
            prompt_in_followup or
            new_prompt in new_body_str or
            urllib.parse.quote_plus(new_prompt) in new_body_str or
            urllib.parse.quote(new_prompt) in new_body_str or
            json.dumps(new_prompt)[1:-1] in new_body_str
        )

        if new_body_str == self.base_body and not prompt_found:
            raise ChatError(
                "SENTINEL_NOT_FOUND",
                f"could not inject the prompt into the recorded body for "
                f"{self.raw.get('host')} -- no known sentinel matched, so the replay would "
                f"re-send the captured probe prompt instead of the caller's."
            )
        # 2. Fire request through the browser-impersonation transport.
        try:
            target_url = self.url
            if "claude.ai" in target_url and "/chat_conversations/" in target_url:
                import re as _re, uuid as _uuid
                target_url = _re.sub(r"/chat_conversations/[^/]+/completion", f"/chat_conversations/{_uuid.uuid4()}/completion", target_url)
            # (Monica's id/prompt surgery now happens deterministically before the
            # sentinel check -- see the api.monica.im branch above.)
            body_bytes = proto_body_bytes if proto_body_bytes is not None else (
                new_body_str.encode("utf-8") if self.base_body else None
            )
            import time as _time
            _send_started_ms = int(_time.time() * 1000)   # v0 poll cutoff: only newer messages count
            r = self._fire(self.method, target_url, self.headers, body_bytes, timeout=60)


            # Only from a non-error reply: a 401/403 body can carry a logged-OUT jar, and storing
            # that would convert a recoverable session into a dead one.
            print("RESPONSE STATUS:", r.status_code, "BODY START:", r.text[:200])
            if r.status_code == 200 and 'INVALID_POW_RESPONSE' in r.text:
                print("GOT INVALID_POW_RESPONSE. Fetching challenge from endpoint...")
                try:
                    # 1. Fetch the challenge payload
                    chal_url = "https://chat.deepseek.com/api/v0/chat/create_pow_challenge"
                    chal_payload = json.dumps({"target_path": "/api/v0/chat/completion"}).encode("utf-8")

                    # We must use the same headers (especially Authorization and cookies)
                    chal_headers = self.headers.copy()
                    chal_headers["content-type"] = "application/json"

                    chal_r = self._fire("POST", chal_url, chal_headers, chal_payload, timeout=30)
                    chal_r.raise_for_status()
                    if chal_r.ok:
                        self._absorb_cookies(chal_r)

                    chal_data = chal_r.json()
                    challenge_obj = chal_data.get("data", {}).get("biz_data", {}).get("challenge", {})
                    if not challenge_obj:
                        raise ChatError("POW_FAILED", "Could not parse challenge object from response")

                    # Normalize snake_case keys from the API to camelCase for the solver
                    # /create_pow_challenge returns expire_at / expire_after but the worker
                    # script (DeepSeek's own code) expects expireAt / expireAfter
                    if "expire_at" in challenge_obj and "expireAt" not in challenge_obj:
                        challenge_obj["expireAt"] = challenge_obj.pop("expire_at")
                    if "expire_after" in challenge_obj and "expireAfter" not in challenge_obj:
                        challenge_obj["expireAfter"] = challenge_obj.pop("expire_after")

                    # 2. Solve the challenge using our standalone Node.js solver
                    import pathlib
                    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "adapters"))
                    from deepseek_adapter import solve_deepseek_pow

                    pow_response = solve_deepseek_pow(json.dumps(challenge_obj))
                    self.headers['x-ds-pow-response'] = pow_response

                    # 3. Re-fire the original completion request with the PoW header attached
                    r = self._fire(self.method, self.url, self.headers, body_bytes, timeout=60)
                except Exception as e:
                    raise ChatError("POW_FAILED", f"DeepSeek PoW failed: {e}")

            if r.ok:
                self._absorb_cookies(r)

            if r.status_code in (401, 403):
                # Keep the provider's non-secret error body attached to the canonical exception.
                # replay_check uses it to distinguish a named CAPTCHA/plan wall from a genuinely
                # rejected credential; dropping it here collapses both into the same AUTH verdict.
                # The body is held in memory only and is never logged by this client.
                exc = SessionExpired("AUTH", "Auth rejected: " + r.text[:100], status=r.status_code)
                exc.raw = r.text
                exc.status = r.status_code
                raise exc

            r.raise_for_status()

        except _TRANSPORT_EXC as e:
            raise ChatError("HTTP_ERROR", str(e))

        # 2b. Multi-step providers: some return a small bootstrap JSON (stream_key /
        # conversation_id) and deliver the real answer on a second request. Detect and
        # follow up before ordinary extraction, which would score the bootstrap as the
        # answer (or as SINGLE_USE because it contains an id field).
        try:
            from multistep_replay import detect_bootstrap, run_followup
        except ImportError:
            import pathlib as _pl, sys as _sys
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from multistep_replay import detect_bootstrap, run_followup
        provider_key = detect_bootstrap(
            r.text,
            host=_up.urlsplit(self.url).netloc,
            has_followup_legs=bool(followup_legs),
        )
        if provider_key:
            # chat_id resolution: the send body is the authority (v0's chat_id names the
            # conversation its poll watches), but some captures carry it only in the URL
            # (referer/query) or in the bootstrap itself. Try, in order: parsed send body,
            # request URL query, bootstrap body -- then give up honestly.
            _chat_id = None
            import re as _re_id
            _follow_leg = _leg2_for(provider_key, self.raw, new_prompt)
            # The recorded Referer often names the chat path (/.../chat/<id>) even when the
            # send body's own chat_id field is empty -- measured on v0.app.  V0's final
            # `/chat/api/chat` leg carries the canonical bare chatId, so inspect it before
            # the first `/chat/api/send` acknowledgement (which may contain a slug prefix).
            _referer = next((v for k, v in self.headers.items() if k.lower() == "referer"), "")
            _id_sources = []
            if provider_key == "v0.app" and _follow_leg:
                _id_sources.append(_follow_leg.get("request_body") or "")
            _id_sources.extend((new_body_str, _up.urlsplit(self.url).query, _referer, r.text))
            for _src in _id_sources:
                try:
                    _obj = json.loads(_src)
                    _cand = _obj.get("chatId") or _obj.get("chat_id")
                    if _cand:
                        _chat_id = str(_cand)
                        break
                except Exception:
                    m = _re_id.search(r"[?&]chatId=([A-Za-z0-9_-]+)", str(_src) or "")
                    if m:
                        _chat_id = m.group(1)
                        break
                    m = _re_id.search(r"[?&]chat_id=([A-Za-z0-9_-]+)", str(_src) or "")
                    if m:
                        _chat_id = m.group(1)
                        break
                    m = _re_id.search(r"/chat/([A-Za-z0-9_-]+)", str(_src) or "")
                    if m:
                        _chat_id = m.group(1)
                        break
            follow_text, follow_err = run_followup(
                provider_key, r.text, self.headers,
                self.headers.get("Cookie") or self.raw.get("cookie_header", ""),
                timeout=90.0,
                chat_id=_chat_id, started_ms=_send_started_ms,
                # Multi-exchange captures (recorded_exchanges, capture_sessions_cdp
                # buffering): the follow-up replays the SECOND leg with values from the
                # first response threaded forward. The leg-2 body gets the same sentinel
                # substitution leg-1 got, so the caller's prompt -- not the recorded
                # probe -- is what the pipeline answers.
                leg2=_follow_leg,
                legs=followup_legs,
                proxy=getattr(self, "proxy", None),
                cookie_absorber=self._absorb_cookies,
                extractor=self._extract_response,
            )
            if follow_text:
                # The no-tool envelope is never the model's words (see unwrap_no_tool_text).
                follow_text = unwrap_no_tool_text(follow_text) or follow_text
                return {
                    "text": follow_text,
                    "label": f"universal-adapter+multistep:{provider_key}",
                    "status": r.status_code,
                    "raw": r.text,
                }
            if provider_key in ("v0.app", "generic_multistep") and follow_err:
                # V0's bootstrap is only an acknowledgement. Returning it as the
                # assistant answer would turn a dropped/failed submit into false
                # capacity, so surface the follow-up failure instead.
                e = ChatError("UPSTREAM_ERROR", follow_err)
                # Preserve the follow-up's own HTTP status for replay_check.  The
                # bootstrap is normally HTTP 200 `ok`, so attaching it here would
                # hide a final-leg 401/403 as a misleading NO_ANSWER result.
                e.raw = follow_err
                e.status = _followup_http_status(follow_err, r.status_code)
                raise e
            # follow-up failed: fall through to normal extraction so the bootstrap
            # is at least reported honestly rather than swallowed.

        # 3. Extract final answer (including binary Protobuf / gRPC-Web response extraction if applicable)
        resp_ct = str(getattr(r, "headers", {}).get("content-type") or "").lower()
        raw_resp_bytes = getattr(r, "content", None)
        if isinstance(raw_resp_bytes, bytes) and raw_resp_bytes and (
            any(tok in resp_ct for tok in ("protobuf", "grpc-web", "connect+proto", "octet-stream"))
            or _is_grpc_web_framed(raw_resp_bytes)
        ):
            proto_strs = [s for s in extract_protobuf_strings(raw_resp_bytes) if not self._is_echo(s)]
            if proto_strs:
                assembled_proto = self._accumulate(proto_strs).strip()
                if assembled_proto:
                    assembled_proto = unwrap_no_tool_text(assembled_proto) or assembled_proto
                    return {
                        "text": assembled_proto,
                        "label": "universal-adapter+protobuf",
                        "status": r.status_code,
                        "raw": assembled_proto,
                    }

        final_text, err = self._extract_response(r.text)
        if not final_text and err:
            e = ChatError("UPSTREAM_ERROR", err)
            # The keyword-search unlock needs the body even when no parser assembled it: a
            # computed answer sitting in an unrecognised envelope is still a live replay.
            e.raw = r.text
            e.status = r.status_code
            raise e

        # The tool contract's no-tool envelope ({"tool": null, "text": ...}) is OUR wire format,
        # never the model's words. Seats whose recorded request carries the contract (Cohere's
        # captured exchange does) answer EVERY probe inside it -- escaped inside their SSE
        # stream -- and without this unwrap the strict numeric verify fails on wire format
        # while the model's answer is sitting right there in .text.
        final_text = unwrap_no_tool_text(final_text) or final_text

        return {
            "text": final_text,
            "label": "universal-adapter",
            "status": r.status_code,
            "raw": r.text,
        }
