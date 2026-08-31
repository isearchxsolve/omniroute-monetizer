"""Multi-step replay: providers whose answer arrives on a SECOND request after a bootstrap POST.

Pattern (Felo, Mistral, and similar):
  1. POST the recorded exchange with the sentinel swapped for the caller's prompt.
     The provider returns a small JSON bootstrap: {"stream_key": "...", "message_id": "...", ...}
  2. GET a stream/poll endpoint using a value from the bootstrap (stream_key, task_id, etc.)
     with the same Authorization header. The answer arrives as SSE or chunked JSON.

This module implements step 2 for each known provider shape. It is called by
universal_replay.py when the bootstrap response is detected, and by replay_check.py
so these providers are scored correctly instead of being misclassified as SINGLE_USE.

Law 4 still holds: the recorded POST is replayed byte-for-byte with one substitution.
The second request is a deterministic follow-up using values from the first response.
"""
import json
import re
import time
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

import requests

# --- Browser-impersonation transport (same rationale as universal_replay.py) ---
# The follow-up GET is fingerprinted exactly like the bootstrap POST; a plain
# requests client can pass step 1 and still be rejected on step 2.
try:
    import curl_cffi
    from curl_cffi.requests import exceptions as _cc_exc
    _HAVE_CURL_CFFI = True
    _STREAM_EXC = (_cc_exc.RequestException, requests.exceptions.RequestException)
except ImportError:
    curl_cffi = None
    _HAVE_CURL_CFFI = False
    _STREAM_EXC = (requests.exceptions.RequestException,)

_IMPERSONATE = "chrome"


def _stream_get(url: str, headers: Dict[str, str], timeout: float):
    """GET a streaming endpoint through the impersonation transport."""
    if _HAVE_CURL_CFFI:
        return curl_cffi.request(
            "GET", url, headers=headers, timeout=timeout,
            impersonate=_IMPERSONATE, default_headers=False, stream=True)
    return requests.get(url, headers=headers, timeout=timeout, stream=True)


def _iter_text_chunks(r):
    """Decoded text chunks from either transport's streamed response.

    curl_cffi's iter_content does NOT support decode_unicode=True (it raises
    NotImplementedError), and chunk_size is ignored. So for curl_cffi we iterate
    raw byte chunks and decode them ourselves. requests supports decode_unicode.
    """
    if _HAVE_CURL_CFFI and isinstance(r, curl_cffi.requests.Response):
        for chunk in r.iter_content():
            yield chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk
        return
    try:
        for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
            yield chunk
    except (TypeError, NotImplementedError):
        for chunk in r.iter_content():
            yield chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk


# ---------------------------------------------------------------------------
# Pre-flight body mutations: fields that must be fresh on every replay.
# These are NOT adapters (Law 4 holds — the recorded request is still replayed
# byte-for-byte except for the sentinel swap); they refresh client-generated
# identifiers that the server rejects if reused.
# ---------------------------------------------------------------------------

def _mistral_preflight(body_str: str) -> str:
    """Mistral Le Chat: messageId is a client-generated UUID that must be unique
    per message. Reusing the recorded one gives 409 'message with the same id
    already exists'. Mint a fresh one."""
    try:
        body = json.loads(body_str)
        if "messageId" in body:
            body["messageId"] = str(uuid.uuid4())
        return json.dumps(body)
    except Exception:
        return body_str


def _claude_preflight(body_str: str) -> str:
    """Claude Official Web: turn_message_uuids and completion_request_id are
    client-generated UUIDs that must be unique per turn. Reusing the recorded ones
    gives 409 'duplicate_human_message_uuid'. Mint fresh UUIDs."""
    try:
        body = json.loads(body_str)
        if "turn_message_uuids" in body and isinstance(body["turn_message_uuids"], dict):
            body["turn_message_uuids"]["human_message_uuid"] = str(uuid.uuid4())
            body["turn_message_uuids"]["assistant_message_uuid"] = str(uuid.uuid4())
        if "completion_request_id" in body:
            body["completion_request_id"] = str(uuid.uuid4())
        return json.dumps(body)
    except Exception:
        return body_str


def _v0_preflight(body_str: str) -> str:
    """v0.app: message_id is a client-generated UUID that must be unique per send.
    Re-sending the recorded one re-answers an already-answered message: the send
    'succeeds' (the 2-byte ok ack) but no NEW assistant message ever appears and the
    poll times out with the caller's prompt scored against the old ack. Mint a fresh
    one. chat_id is deliberately KEPT -- it names the conversation the poll watches,
    and v0_followup polls that exact chat for a message newer than our send."""
    try:
        body = json.loads(body_str)
        if "message_id" in body:
            body["message_id"] = str(uuid.uuid4())
        return json.dumps(body)
    except Exception:
        return body_str


PREFLIGHT_REGISTRY: Dict[str, Callable[[str], str]] = {
    "chat.mistral.ai": _mistral_preflight,
    "claude.ai": _claude_preflight,
    "v0.app": _v0_preflight,
}



def apply_preflight(host: str, body_str: str) -> str:
    """Apply any registered pre-flight mutation for this host."""
    fn = PREFLIGHT_REGISTRY.get(host)
    if fn:
        return fn(body_str)
    return body_str


# ---------------------------------------------------------------------------
# Felo: POST -> bootstrap {stream_key} -> GET /api/message/v1/stream/{key}
# ---------------------------------------------------------------------------

def felo_followup(
    bootstrap_body: str,
    recorded_headers: Dict[str, str],
    cookie_header: str,
    timeout: float = 60.0,
) -> Tuple[Optional[str], Optional[str]]:
    """Given the bootstrap response body, fetch the answer from the Felo stream.

    Returns (answer_text, error). Exactly one is non-None.
    """
    try:
        boot = json.loads(bootstrap_body)
    except Exception:
        return None, "FELLO_BOOTSTRAP_NOT_JSON"

    stream_key = boot.get("stream_key") or boot.get("message_id")
    if not stream_key:
        return None, "FELLO_NO_STREAM_KEY"

    auth = recorded_headers.get("Authorization") or recorded_headers.get("authorization") or ""
    url = f"https://felo.ai/api/message/v1/stream/{stream_key}?offset=0"
    headers = {
        "Accept": "text/event-stream",
        "Authorization": auth,
        "Referer": "https://felo.ai/",
        "User-Agent": recorded_headers.get("User-Agent", "Mozilla/5.0"),
    }

    try:
        r = _stream_get(url, headers, timeout)
    except _STREAM_EXC as e:
        return None, f"FELLO_STREAM_HTTP: {e}"

    if r.status_code != 200:
        return None, f"FELLO_STREAM_{r.status_code}"

    # Parse SSE events, accumulate answer text
    answer_parts: list[str] = []
    start = time.time()
    buf = ""
    for chunk in _iter_text_chunks(r):
        buf += chunk
        while "\n\n" in buf:
            event_block, buf = buf.split("\n\n", 1)
            for line in event_block.split("\n"):
                if not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line[5:].strip())
                except Exception:
                    continue
                content_str = data.get("content", "")
                if not content_str:
                    continue
                try:
                    content = json.loads(content_str)
                except Exception:
                    continue
                cdata = content.get("data", {})
                if isinstance(cdata, dict):
                    ctype = content.get("type", "")
                    text = cdata.get("text", "")
                    if text and ctype == "message" and cdata.get("status") not in ("initializing",):
                        answer_parts.append(text)
                    inner = cdata.get("data", {})
                    if isinstance(inner, dict):
                        t2 = inner.get("text", "") or inner.get("content", "")
                        if t2:
                            answer_parts.append(t2)
        if time.time() - start > timeout:
            break

    answer = "".join(answer_parts).strip()
    if not answer:
        return None, "FELLO_STREAM_EMPTY"
    return answer, None


# ---------------------------------------------------------------------------
# Mistral: POST -> bootstrap -> second stream (tRPC-style numbered chunks)
# ---------------------------------------------------------------------------

def mistral_followup(
    bootstrap_body: str,
    recorded_headers: Dict[str, str],
    cookie_header: str,
    timeout: float = 60.0,
) -> Tuple[Optional[str], Optional[str]]:
    """Mistral Le Chat: the POST returns a bootstrap; the answer arrives on a
    second SSE stream at a conversation-specific URL. The bootstrap body contains
    the conversation_id needed to construct the stream URL."""
    try:
        boot = json.loads(bootstrap_body)
    except Exception:
        return None, "MISTRAL_BOOTSTRAP_NOT_JSON"

    # Mistral's bootstrap typically contains a message or conversation reference
    # The stream URL pattern: /api/chat/{conversation_id}/stream
    conv_id = boot.get("conversation_id") or boot.get("id") or ""
    if not conv_id:
        # Try to extract from the response structure
        for key in ("message", "data"):
            sub = boot.get(key)
            if isinstance(sub, dict):
                conv_id = sub.get("conversation_id") or sub.get("id") or ""
                if conv_id:
                    break
    if not conv_id:
        return None, "MISTRAL_NO_CONV_ID"

    auth = recorded_headers.get("Authorization") or recorded_headers.get("authorization") or ""
    url = f"https://chat.mistral.ai/api/chat/{conv_id}/stream"
    headers = {
        "Accept": "text/event-stream",
        "Authorization": auth,
        "Cookie": cookie_header,
        "Referer": "https://chat.mistral.ai/",
        "User-Agent": recorded_headers.get("User-Agent", "Mozilla/5.0"),
    }

    try:
        r = _stream_get(url, headers, timeout)
    except _STREAM_EXC as e:
        return None, f"MISTRAL_STREAM_HTTP: {e}"

    if r.status_code != 200:
        return None, f"MISTRAL_STREAM_{r.status_code}"

    # Mistral uses tRPC-style numbered chunks: "15:{json}"
    answer_parts: list[str] = []
    start = time.time()
    for chunk in _iter_text_chunks(r):
        # Look for JSON payloads in the stream
        for m in re.finditer(r'\{[^{}]*"content"\s*:\s*"((?:[^"\\]|\\.)*)"', chunk):
            answer_parts.append(m.group(1))
        if time.time() - start > timeout:
            break

    answer = "".join(answer_parts).strip()
    if not answer:
        return None, "MISTRAL_STREAM_EMPTY"
    return answer, None


# ---------------------------------------------------------------------------
# Mistral tRPC JSON-patch stream parser (response-shape handler, not an adapter)
# ---------------------------------------------------------------------------

def looks_like_trpc_stream(text: str) -> bool:
    """True when the body is a tRPC/React-Query numbered-line stream: lines like
    `15:{...json...}` or `8:null`. Mistral Le Chat answers the POST itself in this
    shape, so it must be parsed as a response envelope, not a bootstrap."""
    if not text:
        return False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    pat = re.compile(r"^\d+:(\{.*\}|null|\[.*\])$")
    hits = sum(1 for ln in lines if pat.match(ln.strip()))
    return hits >= 1 and hits >= len(lines) // 2


def mistral_patch_stream_parse(raw_body: str) -> Optional[str]:
    """Parse Mistral Le Chat's JSON-patch SSE stream into the final answer text.

    Stream lines look like:
      15:{"json":{"type":"message","messageId":"...","patches":[
            {"op":"replace","path":"/contentChunks","value":[{"type":"text","text":"5"}]},
            {"op":"append","path":"/contentChunks/0/text","value":"8"}]}}

    We accumulate text per messageId: 'replace' on /contentChunks resets it,
    'append' on /contentChunks/N/text extends it. The assistant answer is the
    message whose generationStatus reaches 'success' (or the fullest one).
    """
    texts: Dict[str, list] = {}
    done: Dict[str, bool] = {}
    for line in raw_body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\d+:(.*)$", line)
        payload = m.group(1) if m else line
        if payload == "null" or not payload.startswith("{"):
            continue
        try:
            ev = json.loads(payload)
        except Exception:
            continue
        j = ev.get("json") or {}
        if j.get("type") != "message":
            continue
        mid = j.get("messageId") or "?"
        for patch in j.get("patches") or []:
            op = patch.get("op")
            path = patch.get("path") or ""
            val = patch.get("value")
            if op == "replace" and path == "/contentChunks" and isinstance(val, list):
                texts[mid] = []
                for chunk in val:
                    if isinstance(chunk, dict) and chunk.get("type") == "text":
                        texts[mid].append(chunk.get("text") or "")
            elif op == "append" and re.match(r"^/contentChunks/\d+/text$", path) and isinstance(val, str):
                texts.setdefault(mid, []).append(val)
            elif op == "replace" and path == "/generationStatus" and val == "success":
                done[mid] = True
    candidates = [(mid, "".join(parts)) for mid, parts in texts.items() if "".join(parts).strip()]
    if not candidates:
        return None
    for mid, txt in candidates:
        if done.get(mid):
            return txt.strip()
    candidates.sort(key=lambda x: len(x[1]), reverse=True)
    return candidates[0][1].strip() or None


# ---------------------------------------------------------------------------
# V0 (v0.app): POST /chat/api/send -> tiny "ok" ack -> poll
# GET /api/chat/chat/latest?chatId=...&lastSyncedAt=... until an assistant
# message newer than our send appears. Discovered by two-way sniff of the live
# tab (2026-08-30): Chrome does exactly this after every send.
# ---------------------------------------------------------------------------

def _v0_text_from_node(node) -> str:
    """Pull text out of v0's message-binary-format: nested tuples like
    ["p", {}, ["text", {}, "58"]] -- collect the 3rd element of every
    ["text", {}, <string>] node, recursively. Tolerates plain-text shapes."""
    if isinstance(node, str):
        return ""
    if isinstance(node, list):
        if len(node) >= 3 and node[0] == "text" and isinstance(node[2], str):
            return node[2]
        return "".join(_v0_text_from_node(child) for child in node)
    if isinstance(node, dict):
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            return node["text"]
        return "".join(_v0_text_from_node(v) for v in node.values())
    return ""


def v0_followup(
    bootstrap_body: str,
    recorded_headers: Dict[str, str],
    cookie_header: str,
    timeout: float = 90.0,
    chat_id: str = None,
    started_ms: int = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Poll the v0 chat-latest endpoint for the assistant message answering OUR send.

    Returns (answer_text, error). Exactly one is non-None. Stale answers are
    rejected by createdAt: only messages created after started_ms (the send
    fire time) count, so a failed send can never score the OLD recorded reply.
    """
    if not chat_id:
        return None, "V0_NO_CHAT_ID"
    started_ms = started_ms or int(time.time() * 1000)
    cutoff_ms = started_ms - 5000          # 5s slack for clock jitter
    url = f"https://v0.app/api/chat/chat/latest?chatId={chat_id}&lastSyncedAt={started_ms}"
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": f"https://v0.app/chat/{chat_id}",
        "User-Agent": recorded_headers.get("User-Agent", "Mozilla/5.0"),
    }
    deadline = time.time() + timeout
    last_err: Optional[str] = None
    while time.time() < deadline:
        try:
            r = _stream_get(url, headers, timeout=15)
        except _STREAM_EXC as e:
            last_err = f"V0_POLL_HTTP: {e}"
            time.sleep(3)
            continue
        if r.status_code != 200:
            last_err = f"V0_POLL_{r.status_code}"
            time.sleep(3)
            continue
        try:
            body = json.loads(r.text)
        except Exception:
            last_err = "V0_POLL_NOT_JSON"
            time.sleep(3)
            continue
        value = (body or {}).get("value") or {}
        for m in reversed(value.get("newMessages") or []):
            if not isinstance(m, dict) or m.get("role") != "assistant":
                continue
            created = str(m.get("createdAt") or "")
            try:
                from datetime import datetime
                created_ms = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                created_ms = 0
            if created_ms and created_ms < cutoff_ms:
                continue                       # pre-dates our send -- stale, keep polling
            if m.get("isContentLoading") or m.get("streaming"):
                time.sleep(3)                  # still generating
                break
            text = _v0_text_from_node(m.get("content") or {}).strip()
            if text:
                return text, None
        time.sleep(3)
    return None, last_err or "V0_NO_NEW_MESSAGE"


# ---------------------------------------------------------------------------
# Registry: host -> followup function
# ---------------------------------------------------------------------------

FOLLOWUP_REGISTRY: Dict[str, Any] = {
    "felo.ai": felo_followup,
    "chat.mistral.ai": mistral_followup,
    "v0.app": v0_followup,
}


def detect_bootstrap(body: str, host: str = None) -> Optional[str]:
    """Detect if a response body is a bootstrap (small JSON with stream/task keys).
    Returns the provider key if recognized, else None."""
    if host and "v0.app" in host and len(body) <= 64 and body.strip().strip('"').lower() == "ok":
        return "v0.app"                        # 2-byte ack -- the answer arrives on the poll
    if len(body) > 2000:
        return None
    try:
        d = json.loads(body)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    # Felo bootstrap signature
    if "stream_key" in d and "task_id" in d:
        return "felo.ai"
    # Mistral bootstrap signature
    if "conversation_id" in d or ("message" in d and isinstance(d.get("message"), dict)):
        return "chat.mistral.ai"
    return None


def run_followup(
    provider_key: str,
    bootstrap_body: str,
    recorded_headers: Dict[str, str],
    cookie_header: str,
    timeout: float = 60.0,
    **extra,
) -> Tuple[Optional[str], Optional[str]]:
    """Dispatch to the appropriate followup handler (extra kwargs passed through)."""
    fn = FOLLOWUP_REGISTRY.get(provider_key)
    if not fn:
        return None, f"NO_FOLLOWUP_FOR_{provider_key}"
    try:
        return fn(bootstrap_body, recorded_headers, cookie_header, timeout, **extra)
    except TypeError:
        # handler predates the extra kwargs
        return fn(bootstrap_body, recorded_headers, cookie_header, timeout)
