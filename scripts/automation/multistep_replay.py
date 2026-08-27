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


PREFLIGHT_REGISTRY: Dict[str, Callable[[str], str]] = {
    "chat.mistral.ai": _mistral_preflight,
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
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
    except requests.exceptions.RequestException as e:
        return None, f"FELLO_STREAM_HTTP: {e}"

    if r.status_code != 200:
        return None, f"FELLO_STREAM_{r.status_code}"

    # Parse SSE events, accumulate answer text
    answer_parts: list[str] = []
    start = time.time()
    buf = ""
    for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
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
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
    except requests.exceptions.RequestException as e:
        return None, f"MISTRAL_STREAM_HTTP: {e}"

    if r.status_code != 200:
        return None, f"MISTRAL_STREAM_{r.status_code}"

    # Mistral uses tRPC-style numbered chunks: "15:{json}"
    answer_parts: list[str] = []
    start = time.time()
    for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
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
# Registry: host -> followup function
# ---------------------------------------------------------------------------

FOLLOWUP_REGISTRY: Dict[str, Any] = {
    "felo.ai": felo_followup,
    "chat.mistral.ai": mistral_followup,
}


def detect_bootstrap(body: str) -> Optional[str]:
    """Detect if a response body is a bootstrap (small JSON with stream/task keys).
    Returns the provider key if recognized, else None."""
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
) -> Tuple[Optional[str], Optional[str]]:
    """Dispatch to the appropriate followup handler."""
    fn = FOLLOWUP_REGISTRY.get(provider_key)
    if not fn:
        return None, f"NO_FOLLOWUP_FOR_{provider_key}"
    return fn(bootstrap_body, recorded_headers, cookie_header, timeout)
