"""veo_session_replay.py — server-side SESSION REPLAY for veoaifree chat (the "omni way").

No browser in the request path. We take the ONE genuine exchange recorded by grab_session.py and
replay it server-side over plain HTTP with the grabbed session cookie — swapping only the query
text, the model, and a fresh frontend_uuid. "dont hit the api hit the cookie the session";
"once cookie in hand pretending to actual browser session".

WHY THIS AND NOT A HAND-BUILT PAYLOAD (measured 2026-08-24): a reconstructed payload trips the
upstream Perplexity classifier — `personal_search.is_true=true` -> "Sign up and repeat your request."
Prompt-framing does NOT reliably dodge it (an anti-search directive passed once, then failed 6/6).
Replaying the GENUINE recorded shape returns HTTP 200 ungated: the same 43-char prompt that was
gated via reconstruction answered cleanly both in-browser and via this server-side replay.

The genuine shape matters, so we preserve it: real Chrome headers (origin/referer/sec-fetch-*/
sec-ch-ua*/user-agent/accept-language), and `is_related:true` with a full `messages[]` history
(the UI always ships history; a bare fresh turn is what looked synthetic).

CONCURRENCY: this is the payoff. No CDP websocket, no single-tab lock -> calls run in parallel
(a thread-safe pooled requests.Session). That is what makes the multi-agent film pipeline viable.

SECRETS: the session lives in the gitignored state/secrets/session_<host>.json written by
grab_session.py. Nothing here ever prints a cookie, header value, or user_name.

    python veo_session_replay.py models
    python veo_session_replay.py chat "prompt" [--model claude-sonnet] [--web]
    python veo_session_replay.py bench [--parallel 4]
"""
from __future__ import annotations
import json
import pathlib
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests

from veoaifree_chat_client import (MODELS, MODELS_MAX, DEFAULT_ID, ChatError,  # reuse the model map
                                   normalize_model, build_payload_fields)

SECRET = pathlib.Path(r"D:\omniroute-monetizer\state\secrets\session_veoaifree_com.json")

# HTTP/2 pseudo-headers and fields requests must compute itself. Everything else in the recorded
# header set is kept verbatim so the request looks exactly like the browser's.
_DROP_HDR = {"content-length", "accept-encoding"}
# Per-model page the UI would have been on; Referer/Origin are part of "looking genuine".
_REFERER = {"claude-sonnet": "https://veoaifree.com/claude/",
            "gemini": "https://veoaifree.com/gemini/",
            "gemini_pro": "https://veoaifree.com/gemini/"}

_TLS = threading.local()


class SessionExpired(ChatError):
    """The grabbed cookie no longer authenticates. A login wall is a correct outcome to report."""


def load_session(path: pathlib.Path = SECRET) -> Dict[str, Any]:
    if not path.exists():
        raise ChatError("NO_SESSION", f"no grabbed session at {path}; run: "
                                      f"python grab_session.py cookie")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "recorded_exchange" not in data:
        raise ChatError("NO_RECORDING", "session file has no recorded_exchange; run: "
                                        "python grab_session.py record  (then send one chat)")
    return data


def build_headers(rec: Dict[str, Any], referer: Optional[str] = None) -> Dict[str, str]:
    """Genuine browser headers from the recording, minus what requests must own."""
    h = {k: v for k, v in (rec.get("request_headers") or {}).items()
         if not k.startswith(":") and k.lower() not in _DROP_HDR}
    h["accept-encoding"] = "gzip, deflate"      # skip br/zstd so decoding is always safe
    if referer:
        h["referer"] = referer
        h["Referer"] = referer
    return h


def build_payload(rec: Dict[str, Any], query: str, label: str, pref: str,
                  history: Optional[List[Dict[str, str]]] = None,
                  web_search: bool = False) -> Dict[str, Any]:
    """The recorded payload with ONLY query/model/uuid/history swapped.

    Keeps the genuine `is_related:true` + populated `messages[]` shape. When the caller has no
    history we reuse the recorded turns and overwrite the trailing user turn with the new query —
    the request then still looks like a continuing conversation, which is what the backend expects.
    """
    tmpl = json.loads(rec["request_body"])
    p = dict(tmpl)
    p["query_str"] = p["prompt"] = query
    p["model"], p["model_preference"] = label, pref
    p["frontend_uuid"] = str(uuid.uuid4())
    p["web_search"] = bool(web_search)
    if history:
        msgs = list(history)
    else:
        msgs = [dict(m) for m in (tmpl.get("messages") or [])]
        if msgs and msgs[-1].get("role") == "user":
            msgs[-1]["content"] = query
        else:
            msgs.append({"role": "user", "content": query})
    p["messages"] = msgs
    p["is_related"] = len(msgs) > 1
    return p


def parse_sse(raw: str) -> Tuple[str, Dict[str, Any]]:
    """Extract the final answer from the Perplexity-style SSE stream.

    The stream sends progressively fuller frames; the last frame carrying answer text wins. Answer
    text shows up as blocks[].markdown_block.answer (and occasionally a top-level answer string).
    Returns (answer, meta) where meta carries the gate signal + frame count for diagnostics.
    """
    answer, frames, personal_search = "", 0, False
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        frames += 1
        chunk = line[5:].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            obj = json.loads(chunk)
        except Exception:
            continue
        if isinstance(obj.get("personal_search"), dict) and obj["personal_search"].get("is_true"):
            personal_search = True
        for blk in (obj.get("blocks") or []):
            md = blk.get("markdown_block") or {}
            if isinstance(md.get("answer"), str) and md["answer"].strip():
                answer = md["answer"]
        if isinstance(obj.get("answer"), str) and obj["answer"].strip():
            answer = obj["answer"]
    gated = "Sign up and repeat your request" in (answer or raw)
    return answer.strip(), {"frames": frames, "personal_search": personal_search, "gated": gated,
                            "raw_len": len(raw)}


def _session() -> requests.Session:
    """One pooled requests.Session per thread — safe for the parallel calls this whole module exists
    to enable. A shared Session is technically thread-safe for requests but connection reuse is
    cleaner per-thread; either way there is NO single-tab lock like the CDP path had."""
    s = getattr(_TLS, "s", None)
    if s is None:
        s = requests.Session()
        _TLS.s = s
    return s


class VeoSessionClient:
    """Server-side replay client. Same chat() surface as VeoChatClient, no browser, parallel-safe."""

    def __init__(self, secret: pathlib.Path = SECRET, timeout: int = 120):
        self.secret = secret
        self.timeout = timeout
        self._data = load_session(secret)
        self._rec = self._data["recorded_exchange"]
        self._url = self._rec["url"]

    def reload(self) -> None:
        """Re-read the session file (keepalive rewrites it each cycle with the freshest cookie)."""
        self._data = load_session(self.secret)
        self._rec = self._data["recorded_exchange"]
        self._url = self._rec["url"]

    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             web_search: bool = False, allow_max: bool = False,
             timeout: Optional[int] = None) -> Dict[str, Any]:
        label, pref, thinking = normalize_model(model, allow_max=allow_max)
        query, convo, is_related = build_payload_fields(messages)
        history = convo if is_related else None
        payload = build_payload(self._rec, query, label, pref, history=history, web_search=web_search)
        ref = _REFERER.get((model or DEFAULT_ID).split("/")[-1].lower())
        headers = build_headers(self._rec, referer=ref)
        try:
            r = _session().post(self._url, headers=headers, json=payload,
                                timeout=timeout or self.timeout)
        except requests.RequestException as e:
            raise ChatError("NETWORK", str(e)[:200])
        raw = r.text
        if r.status_code in (401, 403) or (r.status_code == 200 and "wp-login" in raw[:2000].lower()):
            raise SessionExpired("HTTP", "session no longer authenticates — re-login + re-grab",
                                 status=r.status_code)
        if r.status_code != 200:
            raise ChatError("HTTP", raw[:300], status=r.status_code)
        answer, meta = parse_sse(raw)
        if meta["gated"]:
            raise ChatError("GATED", "upstream personal_search gate tripped despite genuine replay",
                            status=r.status_code)
        if not answer:
            raise ChatError("EMPTY", f"no answer parsed from {meta['frames']} frames",
                            status=r.status_code)
        return {"text": answer, "model": pref + (" (thinking)" if thinking else ""),
                "label": label, "status": r.status_code, "frames": meta["frames"],
                "raw_len": meta["raw_len"]}

    def list_models(self, allow_max: bool = False) -> List[Dict[str, Optional[str]]]:
        return list(MODELS + MODELS_MAX if allow_max else MODELS)


def _cli() -> int:
    import argparse, time as _t
    ap = argparse.ArgumentParser(description="veoaifree server-side session replay (no browser)")
    ap.add_argument("--secret", default=str(SECRET))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models")
    s = sub.add_parser("chat")
    s.add_argument("prompt")
    s.add_argument("--model", default=DEFAULT_ID)
    s.add_argument("--max", action="store_true")
    s.add_argument("--web", action="store_true")
    b = sub.add_parser("bench", help="fire N chats in parallel to prove the concurrency win")
    b.add_argument("--parallel", type=int, default=4)
    b.add_argument("--model", default="claude-sonnet")

    a = ap.parse_args()
    c = VeoSessionClient(secret=pathlib.Path(a.secret))
    if a.cmd == "models":
        for m in c.list_models(allow_max=True):
            print(f'  {m["id"]:14s} {m["label"]:18s} pref={m["pref"]}')
        return 0
    if a.cmd == "chat":
        t0 = _t.time()
        r = c.chat([{"role": "user", "content": a.prompt}], model=a.model,
                   web_search=a.web, allow_max=a.max)
        print(f'[{r["label"]} | {r["model"]} | {r["frames"]} frames | {int((_t.time()-t0)*1000)}ms]\n')
        print(r["text"])
        return 0
    if a.cmd == "bench":
        from concurrent.futures import ThreadPoolExecutor
        prompts = [f"In one sentence, define film term #{i}: "
                   + ["storyboard", "match cut", "diegetic sound", "blocking",
                      "establishing shot", "match on action", "foley", "rack focus"][i % 8]
                   for i in range(a.parallel)]
        t0 = _t.time()
        def one(q):
            s = _t.time()
            try:
                r = c.chat([{"role": "user", "content": q}], model=a.model)
                return (True, int((_t.time()-s)*1000), r["text"][:60])
            except ChatError as e:
                return (False, int((_t.time()-s)*1000), str(e)[:60])
        with ThreadPoolExecutor(max_workers=a.parallel) as ex:
            res = list(ex.map(one, prompts))
        wall = int((_t.time()-t0)*1000)
        ok = sum(1 for r in res if r[0])
        for good, ms, txt in res:
            print(f'  {"OK " if good else "ERR"} {ms:6d}ms  {txt}')
        serial_est = sum(r[1] for r in res)
        print(f'\n{ok}/{len(res)} ok | wall={wall}ms | sum-of-latencies={serial_est}ms '
              f'| speedup~{serial_est/max(wall,1):.1f}x')
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
