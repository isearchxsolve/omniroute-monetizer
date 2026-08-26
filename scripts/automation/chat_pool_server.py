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

Superset gateway: one config, both kinds of supply
-------------------------------------------------
A client config carries exactly ONE gateway base URL, so pointing it here would normally cut it off
from the paid OmniRoute routes on :20128. Instead this server is a SUPERSET of :20128:

    model starts with "pool/"   -> served here, from a free captured session
    anything else               -> forwarded verbatim to :20128, auth header passed through
    upstream refuses or is down -> served here instead, and the reply says why

That last line is the point. When the paid credits run out, the free pool takes over inside the same
endpoint, with no config swap and no client change. `--no-upstream` turns the forwarding off and makes
this a pool-only server again.

The fallback trigger is deliberately conservative. A model's own answer can easily contain the word
"credit", and treating that as an exhausted account would throw away a paid reply AND burn a free
session for nothing. So the body is only inspected for credit language when the response is already an
error -- a healthy 200 is always passed through untouched.
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

UPSTREAM_DEFAULT = "http://127.0.0.1:20128"   # OmniRoute chat -- the paid/OAuth side
UPSTREAM_TIMEOUT_S = 180.0    # generous: OmniRoute has been measured taking ~60s+ on some routes


def now() -> float:
    return time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slug(host: str) -> str:
    return host.replace(".", "-").replace("_", "-").lower()


# Host labels are mostly packaging: api-cohere-com and www-perplexity-ai carry one real word each.
GENERIC_HOST_WORDS = {"api", "www", "com", "ai", "co", "io", "net", "org", "app", "cloud",
                      "chat", "web", "free", "the", "my", "get", "go"}


def seat_token(provider_name: str) -> str:
    """The one word that identifies a seat: api-cohere-com -> cohere, you-com -> you."""
    parts = [p for p in provider_name.lower().replace(".", "-").replace("_", "-").split("-")
             if p and p not in GENERIC_HOST_WORDS]
    return parts[0] if parts else ""


def claude_alias(provider_name: str) -> str:
    """A Claude-shaped model id for a free-pool seat.

    Claude Code will not accept a model whose id it cannot read as a Claude model, so `pool/you-com`
    is unselectable there no matter how healthy that seat is -- which made the whole free pool
    invisible to the one client that matters. Every seat therefore also advertises
    `pool/claude-sonnet-4-6-<seat>`; the trailing word is what pins the provider.
    """
    tok = seat_token(provider_name)
    return f"pool/claude-sonnet-4-6-{tok}" if tok else "pool/claude-sonnet-4-6"


def resolve_seat(providers: list, target: str):
    """Map the part after `pool/` onto a provider. None means "any healthy seat", not "not found".

    Exact host slugs still win, so `pool/api-cohere-com` keeps working. Otherwise the id is split on
    dashes and matched word-against-word, which is what makes the Claude-shaped aliases resolve
    (`claude-sonnet-4-6-cohere` -> cohere) without a hand-maintained table.

    An id naming no known seat rotates instead of erroring: the ids Claude Code sends are not ours to
    control, and a pool that refuses an unfamiliar name is a pool that answers nothing.
    """
    target = (target or "").lower()
    for p in providers:
        if p.name == target:
            return p
    words = set(target.split("-"))
    for p in providers:
        tok = seat_token(p.name)
        if tok and tok in words:
            return p
    return None


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
        self.beats = 0
        self.last_beat_iso = ""
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
            # Idleness is the interesting number, not busyness. A session that keeps serving keeps
            # absorbing rotated cookies and looks after itself; an idle one decays on the provider's
            # own schedule. This is what the heartbeat watches.
            "idleSeconds": None if not self.last_used else round(now() - self.last_used),
            "heartbeats": self.beats,
            "lastHeartbeat": self.last_beat_iso or None,
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

    def acquire(self, deprioritize: tuple = ()) -> Optional[Provider]:
        """Least-recently-used provider that is off cooldown and past its minimum interval.

        Waits briefly rather than failing instantly: with a small pool and a 3s interval, two
        back-to-back requests would otherwise 503 even though the pool is perfectly healthy.

        `deprioritize` is a tuple of host/name substrings (e.g. the dirty-JSON seat). A matching
        provider is used ONLY when no clean seat can answer -- clean-ready first; if none are ready
        we wait for a clean seat that is merely cooling; only when every clean seat is walled/dead,
        or the wait budget is spent, do we hand back the deprioritized one. A dirty reply still beats
        a 503, and the caller can reject it -- but the clean seats are exhausted first. An empty
        tuple (the default, every non-JSON request) makes this identical to plain LRU.
        """
        def demoted(p: Provider) -> bool:
            hay = f"{p.host} {p.name}".lower()
            return any(d in hay for d in deprioritize)

        deadline = now() + WAIT_FOR_SLOT_S
        while True:
            with self.pick_lock:
                ready = [p for p in self.providers if p.ready()]
                preferred = [p for p in ready if not demoted(p)]
                clean_up = [p for p in self.providers if p.available() and not demoted(p)]
                take_demoted = (not clean_up) or now() >= deadline
                candidates = preferred or (ready if take_demoted else [])
                if candidates:
                    pick = min(candidates, key=lambda p: p.last_used)
                    pick.last_used = now()
                    if deprioritize and demoted(pick):
                        log(f"  json-intent: no clean seat available, falling back to {pick.name}")
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


# Language that means the PAID side has nothing left to give, so the free pool should answer instead.
# Only ever matched against a response already known to be an error (see Upstream.forward), because a
# model's own prose about "credits" or "quota" must not be mistaken for an exhausted account.
CREDIT_HINTS = ("credit", "quota", "insufficient", "billing", "payment", "exhausted", "balance",
                "no active credentials", "rate limit", "too many requests", "unauthorized",
                "forbidden", "expired")


# you.com is the one pool seat that regularly answers HTTP 200 with DIRTY json -- prose wrapped around
# the object, code fences, trailing commas. Harmless for free-form chat, poison for a caller parsing
# strict JSON: oioi's film planner gets unparseable output ~1 request in 4 (measured: 73% of pool
# replies were clean, and every dirty one was you.com) and silently builds a storyless board from the
# garbage -> junk stills. So when a prompt is asking for JSON, you.com is demoted to last-resort in
# acquire(): a cleaner seat answers unless none can. It keeps full capacity for every non-JSON request.
DIRTY_JSON_HOSTS = ("you.com", "you-com")


def wants_json(prompt: str) -> bool:
    return "json" in (prompt or "").lower()


class Upstream:
    """OmniRoute (:20128) seen from here: forward, and say when the caller should fall back.

    Deliberately NOT a streaming proxy. :20128 force-streams SSE even for stream:false, and the reply
    has to be inspected before it can be trusted, so it is buffered whole. That is fine for chat and
    would not be for video -- which is one more reason the two faces stay separate processes.
    """

    def __init__(self, base: str, key: str = ""):
        self.base = (base or "").rstrip("/")
        self.key = key
        self.calls = 0
        self.ok = 0
        self.fallbacks = 0
        self.last_reason = ""

    def forward(self, path: str, raw: bytes, auth: str) -> tuple:
        """Returns (status, text, content_type, fallback_reason).

        A non-empty fallback_reason means "do not serve this response; use the free pool" -- either
        because the paid side refused, or because it is not answering at all.
        """
        import requests
        hdrs = {"content-type": "application/json"}
        tok = auth or (f"Bearer {self.key}" if self.key else "")
        if tok:
            hdrs["authorization"] = tok
        self.calls += 1
        try:
            r = requests.post(f"{self.base}{path}", data=raw, headers=hdrs,
                              timeout=UPSTREAM_TIMEOUT_S)
        except Exception as e:
            self.last_reason = f"upstream {self.base} unreachable: {type(e).__name__}"
            self.fallbacks += 1
            return None, "", "", self.last_reason

        text = r.text or ""
        ctype = r.headers.get("content-type", "application/json")
        low = text.lower()

        if r.status_code >= 400:
            hint = next((h for h in CREDIT_HINTS if h in low), None)
            why = (f"upstream HTTP {r.status_code}"
                   + (f" and the body says {hint!r} -- treating the paid side as out"
                      if hint else " -- paid side refused"))
            self.last_reason = why
            self.fallbacks += 1
            return r.status_code, text, ctype, why

        # A 200 that is really an error. Checked narrowly: the body has to look like an error
        # envelope AND carry credit language before a paid answer is thrown away.
        if '"error"' in low and any(h in low for h in CREDIT_HINTS):
            hint = next(h for h in CREDIT_HINTS if h in low)
            why = f"upstream returned 200 with an error envelope mentioning {hint!r}"
            self.last_reason = why
            self.fallbacks += 1
            return r.status_code, text, ctype, why

        self.ok += 1
        return r.status_code, text, ctype, ""

    def models(self) -> list:
        """Upstream's model list, or [] if it will not answer QUICKLY. Never raises.

        6s, not 30s, on purpose. GET /v1/models is a discovery call and the free pool's own entries are
        already in hand, so a slow paid gateway must not decide how long the whole list takes -- at 30s a
        client times out and sees NOTHING, including the healthy pool models. That is the same shape as
        letting one sick seat 500 the capacity endpoint: a caller must never lose the part that works
        because the part that does not work is slow. `x_upstream_reachable: false` in the response is how
        the caller learns the paid side was skipped.
        """
        import requests
        hdrs = {"authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            r = requests.get(f"{self.base}/v1/models", headers=hdrs, timeout=6)
            d = r.json()
        except Exception:
            return []
        rows = d.get("data") if isinstance(d, dict) else None
        return rows if isinstance(rows, list) else []

    def status(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "role": "paid/OAuth routes, tried first for any model not named pool/*",
            "calls": self.calls,
            "ok": self.ok,
            "fellBackToPool": self.fallbacks,
            "lastFallbackReason": self.last_reason or None,
        }


HEARTBEAT_PROMPT = "Reply with only the word: ok"
HEARTBEAT_TICK_MAX_S = 300.0    # how often the thread looks; NOT how often a provider is touched
HEARTBEAT_TICK_MIN_S = 5.0


class Heartbeat(threading.Thread):
    """Keeps idle captured sessions alive by giving them the one thing that actually refreshes them:
    a small amount of real traffic.

    This is the answer to "can we keep the cookies alive". There is no token to refresh -- these are
    browser sessions, not OAuth grants, so `POST /api/providers/{id}/refresh` does nothing for them
    (that is OmniRoute's mechanism, for OmniRoute's connections). What refreshes them is a successful
    request: the provider replies with `Set-Cookie`, and `universal_replay._absorb_cookies` merges it
    back into the jar on disk. A session that serves traffic therefore renews itself, and an IDLE
    session is the one that dies. So the "keepalive" is simply: make sure nothing sits idle too long.

    Three properties make this safe rather than a hammer:

      * It runs INSIDE the pool process and takes the provider's own lock. A separate keepalive process
        would replay the same session concurrently, rotate the cookie under the pool's in-memory copy,
        and break the next real request -- the failure would look like a dead provider and be blamed on
        the provider.
      * It is a FLOOR, not a schedule. A provider that real traffic already touched inside the window
        is skipped, so a busy pool costs nothing extra. Only genuine idleness triggers a call.
      * At most one provider per tick, and a failure goes through the same `stand_down` path as a real
        request -- so a walled or dead session is dropped, never retried in a loop. A keepalive that
        keeps knocking on a wall is worse than no keepalive.
    """

    def __init__(self, pool: "Pool", idle_hours: float):
        super().__init__(daemon=True, name="heartbeat")
        self.pool = pool
        self.idle_s = idle_hours * 3600.0
        # A tenth of the window, clamped. Checking every 5 minutes for a 6-hour window is pointless
        # precision, and it also makes a short window untestable -- which is how a keepalive ships
        # unproven and is discovered dead months later.
        self.tick_s = min(HEARTBEAT_TICK_MAX_S, max(HEARTBEAT_TICK_MIN_S, self.idle_s / 10.0))
        self.beats = 0
        self.failures = 0
        self.skipped_busy = 0
        self.last_note = ""
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _due(self) -> Optional["Provider"]:
        """The single stalest provider that is idle past the window, or None."""
        best, best_idle = None, -1.0
        for p in self.pool.providers:
            if not p.available():
                continue                       # cooling: leave it entirely alone
            if p.last_used:
                idle = now() - p.last_used
            else:
                # Not touched in this process. Fall back to the file's own rotation stamp so a restart
                # does not re-beat everything at once.
                #
                # A provider with NO stamp ranks as maximally stale, not minimally. Most providers
                # never rotate a cookie at all, so "no stamp" is the normal case, and an earlier
                # version used a small sentinel here -- which made every never-stamped provider lose
                # to the one provider that does rotate. Measured: aymo took 4 beats in 40s while the
                # other four were never touched. Unknown freshness is the weakest state, so it wins.
                stamp = self._file_stamp(p)
                idle = (now() - stamp) if stamp else float("inf")
            if idle < self.idle_s:
                self.skipped_busy += 1
                continue
            if idle > best_idle:
                best, best_idle = p, idle
        return best

    @staticmethod
    def _file_stamp(p: "Provider") -> float:
        """Monotonic-clock equivalent of when the session file was last rotated, or 0 if never."""
        try:
            disk = json.loads(p.path.read_text(encoding="utf-8"))
            stamp = disk.get("cookieRotatedAt")
            if not stamp:
                return 0.0
            t = time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
            return now() - max(0.0, time.time() - t)
        except Exception:
            return 0.0

    def run(self) -> None:
        # Wait one tick before the first beat: at startup every provider looks maximally idle, and
        # beating all of them the moment the server comes up is a burst, which is the thing to avoid.
        while not self._stop.wait(self.tick_s):
            try:
                p = self._due()
                if p is None:
                    continue
                with p.lock:                      # cannot overlap a real request, ever
                    if not p.available():         # re-check under the lock
                        continue
                    started = time.perf_counter()
                    try:
                        res = p.client().chat([{"role": "user", "content": HEARTBEAT_PROMPT}])
                        text = str((res or {}).get("text") or "").strip()
                        if not text:
                            raise RuntimeError("empty reply")
                        ms = round((time.perf_counter() - started) * 1000)
                        p.last_used = now()
                        p.beats += 1
                        p.last_beat_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        self.beats += 1
                        self.last_note = f"{p.name} kept warm"
                        log(f"  heartbeat {p.name:22s} OK   {ms:6d}ms")
                    except Exception as e:
                        cd, reason = classify_failure(f"{type(e).__name__}: {e}")
                        p.stand_down(cd, f"heartbeat {reason}: {type(e).__name__}")
                        self.failures += 1
                        self.last_note = f"{p.name} failed its heartbeat: {reason}"
                        log(f"  heartbeat {p.name:22s} FAIL {reason} (cooling {int(cd)}s)")
            except Exception as e:
                # A heartbeat must never be able to take the server down with it.
                self.last_note = f"heartbeat thread error: {type(e).__name__}"

    def status(self) -> dict[str, Any]:
        return {
            "idleWindowHours": round(self.idle_s / 3600.0, 2),
            "tickSeconds": self.tick_s,
            "beatsSent": self.beats,
            "beatFailures": self.failures,
            "note": self.last_note or "no beat needed yet",
            "mechanism": ("traffic, not token refresh -- a successful reply carries Set-Cookie which "
                          "is absorbed back into the jar on disk"),
        }


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
    upstream: Optional[Upstream] = None                 # None => pool-only, no forwarding
    heartbeat: Optional[Heartbeat] = None               # None => no idle-session keepalive
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
        self._raw = b""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0:
            return {}
        # The raw bytes are kept because a forwarded request must reach :20128 byte-for-byte.
        # Re-serialising the parsed dict would drop any field this server does not model, and those
        # fields (tools, thinking budgets, cache_control) are exactly what the paid routes are for.
        self._raw = self.rfile.read(n)
        try:
            return json.loads(self._raw.decode("utf-8", "replace"))
        except ValueError:
            return None

    def _send_raw(self, code: int, text: str, ctype: str) -> None:
        """Relay an upstream reply unchanged. Content-Type is carried over so an SSE body still
        announces itself as SSE, even though it arrived here fully buffered."""
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype or "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Pool-Source", "upstream")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _err(self, code: int, kind: str, msg: str) -> None:
        self._send(code, {"type": "error", "error": {"type": kind, "message": msg}})

    # ---- routes ---------------------------------------------------------------------------

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/health", "/"):
            st = self.pool.status()
            st["upstream"] = self.upstream.status() if self.upstream else {
                "base": None, "role": "disabled (--no-upstream): pool-only server"}
            st["heartbeat"] = self.heartbeat.status() if self.heartbeat else {
                "idleWindowHours": None,
                "note": "disabled (--heartbeat-hours 0): idle sessions will decay on the provider's "
                        "own schedule until real traffic or a re-capture refreshes them",
            }
            self._send(200, st)
        elif path == "/v1/models":
            # The advertised id is the Claude-shaped alias, because an id Claude Code will not accept
            # is a seat no operator can select. The host slug still resolves if sent, and is reported
            # here so `/v1/models` remains readable as a map of which real account is behind which id.
            mine, seen = [], set()
            for p in self.pool.providers:
                mid = claude_alias(p.name)
                if mid in seen:                      # two hosts sharing one word: keep ids unique
                    mid = f"pool/claude-sonnet-4-6-{p.name}"
                seen.add(mid)
                mine.append({"id": mid, "object": "model", "owned_by": p.host,
                             "source": "pool", "state": p.status()["state"],
                             "x_host_id": f"pool/{p.name}"})
            # `pool/claude-sonnet-4-6` is advertised explicitly. It is the id a client should normally
            # send, and a model that never appears in a list is a model no client will ever pick.
            mine.insert(0, {"id": "pool/claude-sonnet-4-6", "object": "model", "owned_by": "pool",
                            "source": "pool", "state": "rotates over every healthy provider",
                            "x_host_id": "pool/auto"})
            up = []
            if self.upstream:
                for row in self.upstream.models():
                    if isinstance(row, dict) and row.get("id"):
                        r = dict(row)
                        r["source"] = "upstream"
                        up.append(r)
            # Upstream first: those are the paid routes, and a client that takes the head of the list
            # should get the good one while credits last.
            self._send(200, {"object": "list", "data": up + mine,
                             "x_upstream_reachable": bool(up) if self.upstream else None})
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
        model = str(body.get("model") or "")

        # ---- superset routing --------------------------------------------------------------
        # Anything not named pool/* belongs to the paid side first. One attempt, never retried:
        # if :20128 refuses, the reason is a wall or a drained account, and neither clears on a
        # retry -- so the free pool answers instead and says why in the reply.
        fb = ""
        if self.upstream and not model.startswith("pool/"):
            code, text, ctype, fb = self.upstream.forward(
                path, self._raw, self.headers.get("Authorization") or "")
            if not fb:
                log(f"  upstream {model or '(default)':26s} OK   HTTP {code}")
                self._send_raw(code, text, ctype)
                return
            log(f"  upstream {model or '(default)':26s} -> pool: {fb}")

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
            if fb:
                detail = f"upstream fell back ({fb}) and the pool could not cover it: {detail}"
            self._err(503, "overloaded_error", detail)
            return

        if anthropic:
            out = {
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
            }
        else:
            out = {
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
            }
        if fb:
            # Stated in the reply, not just the log: a caller that silently got a free-tier answer
            # instead of the paid model it asked for needs to be able to see that.
            out["x_pool_fallback_reason"] = fb
        self._send(200, out)

    # ---- dispatch -------------------------------------------------------------------------

    def _dispatch(self, prompt: str, want: Optional[str]) -> tuple:
        """Try providers in LRU order until one answers. Returns (text, provider_name, detail).

        Each provider is tried at most ONCE per request. Retrying the same session inside one request
        is hammering it, and the failures worth retrying (a wall, a dead cookie) are exactly the ones
        that will not clear in milliseconds.
        """
        pinned = None
        # `pool/auto` and `pool/any` are the natural things for a client to send when it does not
        # care which provider answers, so they mean "no pin" rather than "no such provider". So does
        # a bare Claude-shaped alias with no seat word in it (`pool/claude-sonnet-4-6`).
        if want and want.startswith("pool/") and want.split("/", 1)[1].lower() not in ("auto", "any"):
            target = want.split("/", 1)[1].lower()
            pinned = resolve_seat(self.pool.providers, target)
            if pinned is None:
                log(f"{want!r} names no seat -- rotating instead of refusing")

        # An explicit pin is always honoured (the client asked for you.com, it gets you.com). Only the
        # rotating path deprioritizes the dirty-JSON seat, and only when the prompt is asking for JSON.
        demote = DIRTY_JSON_HOSTS if wants_json(prompt) else ()
        tried = set()
        attempts = 1 if pinned else max(1, len(self.pool.providers))
        for _ in range(attempts):
            p = pinned if pinned else self.pool.acquire(deprioritize=demote)
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
    ap.add_argument("--upstream", default=UPSTREAM_DEFAULT,
                    help=f"OmniRoute chat base URL to forward non-pool models to "
                         f"(default {UPSTREAM_DEFAULT})")
    ap.add_argument("--no-upstream", action="store_true",
                    help="do not forward anything; serve only pool/* from captured sessions")
    ap.add_argument("--upstream-key", default="",
                    help="bearer token for upstream when the caller sends no Authorization header")
    ap.add_argument("--heartbeat-hours", type=float, default=6.0,
                    help="touch a session that has been idle this long, to absorb a fresh cookie. "
                         "0 disables. This is the only working cookie keepalive: there is no token to "
                         "refresh, only traffic.")
    a = ap.parse_args()

    pool = Pool(serve_all=a.all, allow=[s for s in a.allow.split(",") if s.strip()])
    log(f"chat pool: {len(pool.providers)} provider(s) served "
        f"({'--all override' if a.all else 'REPLAY_OK gate'})")
    for p in pool.providers:
        log(f"    {p.name:26s} {p.host:28s} {p.verdict}")
    if not pool.providers:
        log("nothing to serve; starting anyway so /health can explain why")

    Handler.pool = pool
    if a.no_upstream:
        Handler.upstream = None
        log("upstream: DISABLED -- pool-only. A non-pool model name will be answered by the pool.")
    else:
        Handler.upstream = Upstream(a.upstream, a.upstream_key)
        log(f"upstream: {a.upstream} -- any model not named pool/* goes there first, and falls back "
            f"to the pool if it refuses")
    try:
        srv = PoolServer((a.host, a.port), Handler)
    except OSError as e:
        log(f"cannot bind {a.host}:{a.port} -- {e}. Another pool server is probably already up; "
            f"stop it rather than starting a second one.")
        return 1
    log(f"listening on http://{a.host}:{a.port}  "
        f"(POST /v1/messages | /v1/chat/completions, GET /health, GET /v1/models)")
    if a.heartbeat_hours > 0 and pool.providers:
        Handler.heartbeat = Heartbeat(pool, a.heartbeat_hours)
        Handler.heartbeat.start()
        log(f"heartbeat: a session idle more than {a.heartbeat_hours}h gets one small call so it can "
            f"absorb a fresh cookie (checked every {int(Handler.heartbeat.tick_s)}s, one provider per check)")
    else:
        log("heartbeat: off")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("stopped")
    finally:
        if Handler.heartbeat:
            Handler.heartbeat.stop()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
