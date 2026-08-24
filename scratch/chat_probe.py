"""Diagnose the OmniRoute chat gateway against a REALISTIC agent payload.

Why this exists: 2-token "say hi" probes said gemini/gemini-3.6-flash answered in 3.8s, and on
that basis the film pipeline was pointed at it -- then a 7-stage run burned 497 seconds and died.
A tiny probe measures routing, not capacity. This sends the ACTUAL Scriptwriter system prompt at
the ACTUAL token budget and dumps the RAW response body on failure, because the interesting part
of a gateway failure is always the body ("ALL_ACCOUNTS_INACTIVE", "No cookie auth credentials
found", a rate-limit JSON) and every wrapper above it throws that away.

Usage: python chat_probe.py [port] [model ...]
"""
import json
import sys
import time
import urllib.error
import urllib.request

KEY = "sk-2daf4dd6d1e45047-d60156-541a3aeb"

# The real thing, lifted from orchestrator.py's Scriptwriter agent.
SYSTEM = (
    "You are a professional screenwriter for animated short films. "
    "Given an idea, produce a screenplay broken into scenes. "
    "Respond with ONLY valid JSON, no prose, no markdown fences, in this shape: "
    '{"script": "<full screenplay text>", "characters": [{"name": "...", "description": "..."}], '
    '"scenes": [{"id": 1, "description": "...", "duration": 5, "dialogue": "..."}]}'
)
USER = "A lighthouse keeper who befriends a whale. Exactly 3 scenes. Anime style."


def _from_sse(raw):
    """Collapse an SSE chat-completion stream into the non-streaming envelope shape.

    Returns None if the body is not SSE at all. Joins every choices[0].delta.content and
    delta.reasoning_content in arrival order, and keeps the LAST non-null finish_reason and any
    usage block, because both arrive on trailing chunks.
    """
    if "data:" not in raw:
        return None
    content, reasoning, finish, usage, model_id, cid = [], [], None, None, None, None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except Exception:
            continue
        model_id = chunk.get("model") or model_id
        cid = chunk.get("id") or cid
        usage = chunk.get("usage") or usage
        for ch in chunk.get("choices") or []:
            delta = ch.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
    return {
        "id": cid or "sse", "model": model_id, "usage": usage,
        "choices": [{"index": 0, "finish_reason": finish, "message": {
            "role": "assistant", "content": "".join(content),
            "reasoning_content": "".join(reasoning)}}],
    }


def probe(port, model, max_tokens=4096, json_mode=True):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read().decode("utf-8", "replace")
        dt = time.time() - t0
    except urllib.error.HTTPError as e:
        # THE POINT OF THIS SCRIPT. urllib raises before you can read the body, and every
        # convenience wrapper reports only "HTTP Error 503" -- which names the symptom and hides
        # the cause. The gateway puts the cause in the body.
        return {"model": model, "elapsed": round(time.time() - t0, 1), "http": e.code,
                "body": e.read().decode("utf-8", "replace")[:600]}
    except Exception as e:
        return {"model": model, "elapsed": round(time.time() - t0, 1),
                "err": f"{type(e).__name__}: {e}"}

    out = {"model": model, "elapsed": round(dt, 1), "http": 200}
    try:
        d = json.loads(raw)
    except Exception:
        # MEASURED 2026-08-24: the gateway answers with server-sent events even when the request
        # does NOT set "stream": true. Calling .json() on that body raises "Expecting value: line 1
        # column 1", which reads exactly like a dead provider -- so a whole benchmark scored three
        # WORKING models as failures. Reassemble the deltas before judging anything.
        d = _from_sse(raw)
        if d is None:
            out["err"] = f"neither JSON nor SSE; raw={raw[:400]!r}"
            return out
        out["transport"] = "sse-unrequested"

    if "error" in d and not d.get("choices"):
        # A 200 with an error payload. The gateway does this, and it is the reason a caller that
        # only checks status codes sees "success" and then trips over a missing "choices".
        out["err"] = f"200-with-error: {json.dumps(d['error'])[:400]}"
        return out

    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = msg.get("content") or ""
    out["served"] = d.get("model")
    out["finish"] = ch.get("finish_reason")
    out["chars"] = len(content)
    out["reasoning_chars"] = len(msg.get("reasoning_content") or "")
    out["usage"] = d.get("usage")
    if not content:
        out["err"] = f"empty content; message keys={sorted(msg)}"
        return out
    try:
        parsed = json.loads(content)
        out["scenes"] = len(parsed.get("scenes") or [])
        out["ok"] = out["scenes"] > 0
    except Exception as e:
        out["err"] = f"content not JSON ({e}); head={content[:200]!r}"
    return out


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "20128"
    models = sys.argv[2:] or ["gemini/gemini-3.6-flash"]
    for m in models:
        r = probe(port, m)
        print(json.dumps(r), flush=True)
