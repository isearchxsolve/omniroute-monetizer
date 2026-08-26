#!/usr/bin/env python3
"""An HTTP face for the captured browser sessions, so oioi can actually consume them.

The capture sweep produces `state/secrets/session_*.json` -- replayable browser exchanges against
free provider web UIs. Until now nothing could *call* them: they were files, not a route. This serves
them as an Anthropic-shaped endpoint, which is the shape oioi speaks:

    POST /v1/messages            Anthropic (what oioi calls -- NOT /v1/chat/completions)
    POST /v1/chat/completions    OpenAI shape, for clients that expect it
    GET  /v1/models              one pseudo-model per live provider
    GET  /health                 pool status, per-provider verdict and cooldown

Runs on its own port. :20128 is OmniRoute chat and :8189 is the video router; this is a third face
and must never be merged with either, because a chat pool and a video pool fail differently and a
merged process makes one outage look like the other.

Which sessions get served
-------------------------
Only those a replay check verdicted REPLAY_OK, read from `state/replay_check.json`. This is the whole
point of the gate: 24 captures exist, and on the last honest scoring 5 replayed. Serving all 24 would
recreate this repo's original defect -- a registry advertising 88 working routes when 15 answered.
A capture is not supply. Pass --all to override, and the /health payload will say it was overridden.

Breadth, not depth
------------------
Every one of these is a free account on someone else's web UI. Hammering one is how a seat gets
burned, so selection is least-recently-used across healthy providers, with two independent brakes:

  * MIN_INTERVAL   a provider is not called again until this many seconds have passed
  * cooldown       a provider that fails is stood down for COOLDOWN_S and the next one is tried

A wall (credits/captcha/quota) or an auth refusal puts a provider down for a long cooldown and is
never retried inside a request -- retrying a wall is hammering it. Transport errors get the short
cooldown, because those are usually ours.

No secret is logged. Session files hold cookies and tokens; only the host, the verdict, the latency
and the reply length ever reach stdout or /health.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECRETS = ROOT / "state" / "secrets"
VERDICTS = ROOT / "state" / "replay_check.json"

sys.path.insert(0, str(HERE))

DEFAULT_PORT = 20130

MIN_INTERVAL_S = 3.0          # never call the same provider more often than this
COOLDOWN_FAIL_S = 90.0        # transport / parse failure: probably ours, short stand-down
COOLDOWN_WALL_S = 3600.0      # credits, captcha, quota, auth: long stand-down, never retried
WAIT_FOR_SLOT_S = 8.0         # how long a request will wait for a provider to come off interval


def now() -> float:
    return time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slug(host: str) -> str:
    return host.replace(".", "-").replace("_", "-").lower()


class Provider:
    """One captured session, plus the state needed to not abuse it."""

    def __init__(self, path: pathlib.Path, host: str, verdict: str):
        self.path = path
        self.host = host
        self.verdict = verdict
        self.name = slug(host)
        self.last_used = 0.0
        self.down_until = 0.0
        self.down_reason = ""
        self.calls = 0
        self.ok = 0
        self.fail = 0
        self.lock = threading.Lock()
        self._client = None

    def client(self):
        # Built lazily and reused: construction reads the session file off disk and rebuilds the
        # header set, which is wasted work on every call.
        if self._client is None:
            from universal_replay import UniversalSessionClient
            self._client = UniversalSessionClient(self.path)
        return self._client

    def available(self) -> bool:
        return now() >= self.down_until

    def ready(self) -> bool:
        return self.available() and (now() - self.last_used) >= MIN_INTERVAL_S

    def stand_down(self, seconds: float, reason: str) -> None:
        self.down_until = now() + seconds
        self.down_reason = reason[:160]

    def status(self) -> dict[str, Any]:
        remaining = max(0.0, self.down_until - now())
        return {
            "provider": self.name,
            "host": self.host,
            "captureVerdict": self.verdict,
            "state": "cooling" if remaining else "ready",
            "cooldownSecondsLeft": round(remaining, 1),
            "cooldownReason": self.down_reason or None,
            "calls": self.calls,
            "ok": self.ok,
            "fail": self.fail,
        }


class Pool:
    def __init__(self, serve_all: bool = False, allow: Optional[list] = None):
        self.serve_all = serve_all
        self.allow = [a.lower() for a in (allow or [])]
        self.providers: list[Provider] = []
        self.pick_lock = threading.Lock()
        self._load()

    def _verdict_map(self) -> dict[str, str]:
        if not VERDICTS.exists():
            return {}
        try:
            d = json.loads(VERDICTS.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        out = {}
        for r in d.get("results") or []:
            h = str(r.get("host") or "")
            # Keep the best verdict seen for a host: two capture files can share one host.
            if h and (h not in out or r.get("verdict") == "REPLAY_OK"):
                out[h] = str(r.get("verdict") or "?")
        return out

    def _load(self) -> None:
        verdicts = self._verdict_map()
        if not verdicts and not self.serve_all:
            log(f"WARNING no {VERDICTS.name} -- nothing can be verdicted, so nothing is served. "
                f"Run replay_check.py, or start with --all to override the gate.")
        for p in sorted(SECRETS.glob("session_*.json")):
            try:
                host = str(json.loads(p.read_text(encoding="utf-8")).get("host") or "")
            except (ValueError, OSError):
                continue
            if not host:
                continue
            verdict = verdicts.get(host, "UNKNOWN")
            keep = (verdict == "REPLAY_OK") or self.serve_all \
                or any(a in host.lower() for a in self.allow)
            if not keep:
                continue
            self.providers.append(Provider(p, host, verdict))

    def healthy(self) -> list:
        return [p for p in self.providers if p.available()]

    def acquire(self) -> Optional[Provider]:
        """Least-recently-used provider that is off cooldown and past its minimum interval.

        Waits briefly rather than failing instantly: with a small pool and a 3s interval, two
        back-to-back requests would otherwise 503 even though the pool is perfectly healthy.
        """
        deadline = now() + WAIT_FOR_SLOT_S
        while True:
            with self.pick_lock:
                ready = [p for p in self.providers if p.ready()]
                if ready:
                    pick = min(ready, key=lambda p: p.last_used)
                    pick.last_used = now()
                    return pick
                any_up = [p for p in self.providers if p.available()]
            if not any_up or now() >= deadline:
                return None
            time.sleep(0.25)

    def status(self) -> dict[str, Any]:
        return {
            "pool": "captured browser sessions replayed server-side",
            "gate": "all capture files (--all override)" if self.serve_all
                    else "only sessions verdicted REPLAY_OK by replay_check.py",
            "served": len(self.providers),
            "readyNow": len([p for p in self.providers if p.ready()]),
            "availableNow": len(self.healthy()),
            "minIntervalSeconds": MIN_INTERVAL_S,
            "providers": [p.status() for p in self.providers],
        }


# Wall text is checked on the REPLY, not just the status code, because a replayed browser session
# answers HTTP 200 with the wall rendered in the body far more often than it answers 402.
WALL_HINTS = ("credit", "quota", "billing", "payment", "captcha", "upgrade", "subscribe",
              "limit reached", "insufficient", "unauthorized", "forbidden", "not authenticated",
              "session expired", "auth rejected", "rate limit", "too many requests")


def classify_failure(msg: str) -> tuple[float, str]:
    """(cooldown seconds, short reason). A wall is stood down for an hour and never retried."""
    low = (msg or "").lower()
    if any(w in low for w in WALL_HINTS):
        return COOLDOWN_WALL_S, "wall or auth refusal -- stood down, never hammered"
    return COOLDOWN_FAIL_S, "replay failed"


def flatten(content: Any) -> str:
    """Anthropic allows content as a string or a list of blocks; oioi sends both shapes."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") in (None, "text") and isinstance(b.get("text"), str):
                    parts.append(b["text"])
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return "" if content is None else str(content)


def to_messages(body: dict) -> list:
    """Normalise either wire shape into [{role, content:str}], system prompt folded into the front.

    The system prompt has to become part of the user turn: a replayed browser exchange has exactly
    one prompt field, so there is nowhere else to put it. Dropping it silently would make an agentic
    client's instructions vanish -- the failure would look like the model ignoring its system prompt.
    """
    out = []
    sysmsg = body.get("system")
    if sysmsg:
        out.append({"role": "system", "content": flatten(sysmsg)})
    for m in body.get("messages") or []:
        if not isinstance(m, dict):
            continue
        out.append({"role": str(m.get("role") or "user"), "content": flatten(m.get("content"))})
    return out


def as_single_prompt(messages: list) -> str:
    """Collapse a conversation into one prompt.

    A captured exchange carries a single prompt field, so multi-turn history has to be serialised
    into it. Labelled by role rather than concatenated bare, or the model cannot tell its own prior
    turns from the user's.
    """
    if not messages:
        return ""
    if len(messages) == 1:
        return messages[0]["content"]
    lines = []
    for m in messages[:-1]:
        role = {"system": "System", "assistant": "Assistant", "user": "User"}.get(m["role"], "User")
        if m["content"].strip():
            lines.append(f"{role}: {m['content']}")
    lines.append(f"User: {messages[-1]['content']}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


def approx_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    pool: Pool = None                                   # set on the class before serve_forever
    server_version = "OmniChatPool/1.0"

    def log_message(self, fmt: str, *args) -> None:
        pass                                            # access logging is done deliberately below

    # ---- plumbing -------------------------------------------------------------------------

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self) -> Optional[dict]:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except ValueError:
            return None

    def _err(self, code: int, kind: str, msg: str) -> None:
        self._send(code, {"type": "error", "error": {"type": kind, "message": msg}})

    # ---- routes ---------------------------------------------------------------------------

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/health", "/"):
            self._send(200, self.pool.status())
        elif path == "/v1/models":
            self._send(200, {"object": "list", "data": [
                {"id": f"pool/{p.name}", "object": "model", "owned_by": p.host,
                 "state": p.status()["state"]}
                for p in self.pool.providers
            ]})
        else:
            self._err(404, "not_found", f"no route {path}")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in ("/v1/messages", "/v1/chat/completions"):
            self._err(404, "not_found", f"no route {path}")
            return
        body = self._read_json()
        if body is None:
            self._err(400, "invalid_request_error", "body is not JSON")
            return
        messages = to_messages(body)
        if not messages:
            self._err(400, "invalid_request_error", "no messages in request")
            return
        prompt = as_single_prompt(messages)
        anthropic = path == "/v1/messages"

        text, used, detail = self._dispatch(prompt, body.get("model"))
        if text is None:
            # 503, not 500: the pool is intact, it simply has no provider free right now. A client
            # that retries later succeeds, which is a different instruction than "this broke".
            self._err(503, "overloaded_error", detail)
            return

        if anthropic:
            self._send(200, {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": body.get("model") or f"pool/{used}",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": approx_tokens(prompt),
                          "output_tokens": approx_tokens(text)},
                "x_pool_provider": used,
            })
        else:
            self._send(200, {
                "id": f"chatcmpl-{uuid.uuid4().hex[:20]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model") or f"pool/{used}",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": approx_tokens(prompt),
                          "completion_tokens": approx_tokens(text),
                          "total_tokens": approx_tokens(prompt) + approx_tokens(text)},
                "x_pool_provider": used,
            })

    # ---- dispatch -------------------------------------------------------------------------

    def _dispatch(self, prompt: str, want: Optional[str]) -> tuple:
        """Try providers in LRU order until one answers. Returns (text, provider_name, detail).

        Each provider is tried at most ONCE per request. Retrying the same session inside one request
        is hammering it, and the failures worth retrying (a wall, a dead cookie) are exactly the ones
        that will not clear in milliseconds.
        """
        pinned = None
        # `pool/auto` and `pool/any` are the natural things for a client to send when it does not
        # care which provider answers, so they mean "no pin" rather than "no such provider".
        if want and want.startswith("pool/") and want.split("/", 1)[1].lower() not in ("auto", "any"):
            target = want.split("/", 1)[1].lower()
            pinned = next((p for p in self.pool.providers if p.name == target), None)
            if pinned is None:
                return None, "", f"no provider named {want!r}; see GET /v1/models"

        tried = set()
        attempts = 1 if pinned else max(1, len(self.pool.providers))
        for _ in range(attempts):
            p = pinned if pinned else self.pool.acquire()
            if p is None:
                break
            if p.name in tried:
                break
            tried.add(p.name)
            if pinned and not p.available():
                return None, "", f"{p.name} is cooling: {p.down_reason}"
            if pinned:
                # A pinned provider still gets the minimum-interval brake. Without this a client that
                # names one provider bypasses rotation entirely and hammers a single free account,
                # which is how a seat gets burned.
                deadline = now() + WAIT_FOR_SLOT_S
                while not p.ready() and now() < deadline:
                    time.sleep(0.25)
                if not p.ready():
                    return None, "", (f"{p.name} was called under {MIN_INTERVAL_S}s ago; pinned "
                                      f"providers are rate-limited too")
                p.last_used = now()

            started = time.perf_counter()
            p.calls += 1
            try:
                with p.lock:                      # one in-flight call per session, always
                    res = p.client().chat([{"role": "user", "content": prompt}])
                text = str((res or {}).get("text") or "").strip()
                if not text:
                    raise RuntimeError("empty reply")
                ms = round((time.perf_counter() - started) * 1000)
                p.ok += 1
                log(f"  {p.name:26s} OK   {ms:6d}ms  {len(text)} chars")
                return text, p.name, ""
            except Exception as e:
                ms = round((time.perf_counter() - started) * 1000)
                p.fail += 1
                cd, reason = classify_failure(f"{type(e).__name__}: {e}")
                p.stand_down(cd, f"{reason}: {type(e).__name__}")
                log(f"  {p.name:26s} FAIL {ms:6d}ms  {reason} "
                    f"(cooling {int(cd)}s) {type(e).__name__}")
                if pinned:
                    return None, "", f"{p.name} failed: {reason}"

        if not self.pool.providers:
            return None, "", ("no providers served -- run replay_check.py so sessions can be "
                              "verdicted, or start with --all")
        return None, "", (f"all {len(self.pool.providers)} provider(s) are cooling or failed this "
                          f"request; GET /health for per-provider reasons")


class PoolServer(ThreadingHTTPServer):
    """ThreadingHTTPServer, minus the reuse flag.

    The base class sets `allow_reuse_address = 1`, and on Windows SO_REUSEADDR permits a SECOND
    process to bind a port that is already bound -- it does not raise. Both processes then sit in
    LISTENING and connections land on whichever, so a stale server keeps serving old code and every
    fix appears not to work. Measured on :20130 with two servers up at once. Failing loudly on a
    duplicate bind is the only way that stays visible.
    """
    allow_reuse_address = False
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--all", action="store_true",
                    help="serve every capture file, not just REPLAY_OK ones. Overstates supply; "
                         "/health reports that the gate was overridden.")
    ap.add_argument("--allow", default="",
                    help="comma-separated host substrings to serve regardless of verdict")
    a = ap.parse_args()

    pool = Pool(serve_all=a.all, allow=[s for s in a.allow.split(",") if s.strip()])
    log(f"chat pool: {len(pool.providers)} provider(s) served "
        f"({'--all override' if a.all else 'REPLAY_OK gate'})")
    for p in pool.providers:
        log(f"    {p.name:26s} {p.host:28s} {p.verdict}")
    if not pool.providers:
        log("nothing to serve; starting anyway so /health can explain why")

    Handler.pool = pool
    try:
        srv = PoolServer((a.host, a.port), Handler)
    except OSError as e:
        log(f"cannot bind {a.host}:{a.port} -- {e}. Another pool server is probably already up; "
            f"stop it rather than starting a second one.")
        return 1
    log(f"listening on http://{a.host}:{a.port}  "
        f"(POST /v1/messages | /v1/chat/completions, GET /health, GET /v1/models)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("stopped")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
