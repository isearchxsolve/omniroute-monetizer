"""session_pool.py — the breadth-not-depth ROUTER over every grabbed session (chat OR video).

Operator's rule (2026-08-24): "we don't hammer one provider with parallel tasks. We divide among
multiple providers, multiple accounts, multiple sessions." So this is NOT a way to fan parallel
load at one host — it is a LOAD SPREADER: one light call each, least-recently-used across all live
state/secrets/session_<host>.json, with a per-session cooldown so no single provider ever gets a
burst. Different providers may run concurrently (that IS the point); the SAME host never does
(a per-host lock serializes any sessions that share it, e.g. multiple accounts on one provider).

Modality-agnostic on purpose: chat and video soft targets are grabbed the same way (grab_session.py
records any genuine exchange by --url-substr) and routed the same way here. The only per-provider
thing is the replay ADAPTER — the code that swaps the query into the recorded body and pulls the
answer back out. We dispatch ONLY to hosts whose genuine shape we have PROVEN (veoaifree today via
VeoSessionClient). Unknown hosts are listed but never blind-replayed — we don't guess a shape.

The "omni way": replay the recorded genuine exchange server-side with the grabbed cookie; never
reconstruct the request (reconstruction trips upstream gates — measured). No browser in the request
path, so calls are parallel-safe across hosts.

    python session_pool.py list                    # the pool, metadata only (never prints a secret)
    python session_pool.py chat "prompt" [--model claude-sonnet]   # route ONE call (LRU pick)
    python session_pool.py sweep [--prompt ...] [--workers 6] [--modality chat]  # one light call each
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import pathlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Type

from veoaifree_chat_client import ChatError
from digen_session_replay import DigenSessionClient
from veo_session_replay import VeoSessionClient, SessionExpired
from chrome_replay_client import ChromeReplayClient, CHROME_CLIENTS
from chrome_video_client import ChromeVideoClient, VIDEO_HOSTS

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
# last-used timestamps ONLY (no cookie, no header) so the cooldown spreads load across CLI runs too.
POOL_STATE = pathlib.Path(r"D:\omniroute-monetizer\state\session_pool_state.json")

# host substring -> proven replay client. One line per provider whose genuine shape is captured AND
# verified end-to-end. Dirty-and-easy: add a line when a new provider (chat OR video) proves out.
# We NEVER blind-replay a host without an entry here — an unproven shape is a guess, and guessing is
# exactly what the omni way exists to avoid.
CLIENTS: Dict[str, Type[Any]] = {
    # "veoaifree.com": VeoSessionClient,  # Commented out to force Universal Replay test
    "digen.ai": DigenSessionClient,
}

# Minimum seconds between two calls that land on the SAME session — the breadth-not-depth cooldown.
DEFAULT_COOLDOWN = 20.0


def _client_for(host: str, raw: dict = None) -> Optional[Type[Any]]:
    # An API-CREDENTIAL seat comes first: it carries a bearer token plus a documented contract, so it
    # has no recorded exchange to replay and never will. Dispatch on the declared `api.kind`, not on
    # the host string, so a second account on the same provider needs no new entry anywhere.
    kind = ((raw or {}).get("api") or {}).get("kind")
    if kind == "rtst":
        from rtst_api_client import RtstApiClient
        return RtstApiClient
    if kind == "youcom":
        from youcom_api_client import YouComApiClient
        return YouComApiClient
    if kind == "flow":
        # Flow (labs.google) supply bridge (worklog #1123): the dominant video supply (~2,075
        # credits, ~103 clips) is already served genuinely by video_router.py on :8189; this
        # seat kind makes it visible to the :8190 pool without touching the provider side.
        from flow_api_client import FlowApiClient
        return FlowApiClient
    if kind == "digen":
        # Digen stateless graduation (worklog #1131, operator full-Chrome-independence override
        # #1130): DigenSessionClient replays the recorded Digen-Token job flow over pure HTTP
        # (submit -> poll -> video URL), no browser. Declared api.kind dispatches FIRST, which
        # un-shadows it from the modality=video -> ChromeVideoClient path below. Spend-gated
        # like flow/rtst (OMNI_VIDEO_CONFIRM_SPEND).
        from digen_session_replay import DigenSessionClient
        return DigenSessionClient

    # WEBSOCKET seats (Doctrine 3a, CORRECTED 2026-08-28 per operator): a seat carrying
    # `recorded_ws` was captured by capture_websocket_cdp.py — the site speaks a websocket.
    # The capture is the CHROME BLUEPRINT (evidence of what Chrome does) and is valuable.
    # But the RUNTIME must NOT hand-replay the provider's protocol — that is "playing the
    # provider" (reverse-engineering / copycatting its contract). The doctrine's architecture
    # is to BE CHROME: provide the Chrome blueprint (a real V8 engine via Selenium/Playwright)
    # and let the provider's own JS land on it and play by itself. The provider IS the
    # contract; we are only the environment. So recorded_ws seats deliberately fall through
    # to the Chrome-blueprint dispatch below (ChromeReplayClient), where the provider's own
    # JS opens its own websocket and runs its own protocol by itself. No hand-replay client.
    #
    # OPERATOR OVERRIDE 2026-08-28 (worklog #1130): the "no hand-replay" prohibition above is
    # LIFTED for the full-Chrome-independence push. Hand-rolled stateless clients (PoW/signature
    # recompute, websocket/multi-step replay) are now authorized per-seat; each must pass Law-3
    # computed verification before graduation. Dispatch behavior here changes per-seat as seats
    # graduate (via "runtime": "replay" / api.kind / a dedicated client), not wholesale.

    # GRADUATION LEVER (worklog #1113 — runtime-Chrome is an anti-pattern).
    # Driving a live Chrome tab per request serializes every call through ONE
    # global driver lock (chrome_replay_client._DRIVER_LOCK, held for the WHOLE
    # call) — concurrent requests queue behind a single browser, which is the
    # exact opposite of the breadth-not-depth load spreader this pool exists to
    # be. Chrome is a CAPTURE / onboard / re-auth instrument, not a runtime
    # server. A seat that carries a recorded_exchange (or recorded_job) AND
    # declares "runtime": "replay" is served by the stateless HTTP replay client
    # (curl_cffi browser-TLS impersonation) instead of a live tab — parallel-safe,
    # no browser in the request path. Opt-in per seat: nothing changes until a
    # seat is explicitly graduated, so this is safe by default. Checked BEFORE
    # every Chrome dispatch so a graduated seat never touches a browser.
    if (raw or {}).get("runtime") == "replay" and (
            (raw or {}).get("recorded_exchange") or (raw or {}).get("recorded_job")):
        if (raw or {}).get("recorded_job") and not (raw or {}).get("recorded_exchange"):
            from video_universal_replay import VideoUniversalSessionClient
            return VideoUniversalSessionClient
        if (raw or {}).get("modality") == "video":
            from video_universal_replay import VideoUniversalSessionClient
            return VideoUniversalSessionClient
        # ChatX (worklog #1115): a Laravel app whose CSRF rotates per session and whose
        # answer arrives on a SECOND endpoint (GET /chats_stream SSE) keyed by the
        # conversions_id that POST /sendchat returns. A single-exchange replay cannot
        # serve it; the dedicated 2-leg client performs the full genuine flow per call
        # (fresh CSRF from the page meta -> sendchat -> SSE), still chrome-free.
        if "chatx" in host:
            from chatx_replay import ChatXReplayClient
            return ChatXReplayClient
        from universal_replay import UniversalSessionClient
        return UniversalSessionClient

    # Chrome-doctrine VIDEO seats (worklog #1108): the host's own UI in the live signed-in
    # tab generates the video. Checked FIRST (after API-kind dispatch) so that even hosts
    # with a legacy replay client in CLIENTS (e.g. digen) get the Chrome path when the
    # seat declares modality=video. A dual-modal host (grok.com, gemini.google.com, ...)
    # has BOTH a chat seat (ChromeReplayClient) and a video seat (ChromeVideoClient) —
    # modality picks the path.
    #
    # One Chrome, infinite sites (worklog #1112): a seat may ALSO declare its own video UI
    # inline ("chrome": {"tab": ...}) with NO VIDEO_HOSTS entry. The site's own JS shipped
    # with every page load IS the adapter, so a brand-new video provider needs zero registry
    # code -- ChromeVideoClient builds a generic "ui" spec from the seat file itself.
    if (raw or {}).get("modality") == "video" and (
            host in VIDEO_HOSTS or bool((raw or {}).get("chrome"))):
        return ChromeVideoClient

    for key, cls in CLIENTS.items():
        if key in host:
            return cls

    # Chrome-backed seats (Adapter Thesis, worklog #1094-#1100): these hosts were proven
    # REPLAY_OK only THROUGH the live signed-in Chrome (in-browser fetch or adapter
    # invocation). Python `requests` replay fails for them (CORS / PoW / x-sign / live
    # bearer), so they must be served by driving their own UI in the attached browser.
    # Checked BEFORE the universal fallback so requests-replay never gets a turn.
    #
    # One Chrome, infinite sites (worklog #1112): a seat may declare its own Chrome backing
    # inline ("chrome": {"tab": "chat.newsite.com"} or "chrome": true) with NO CHROME_CLIENTS
    # entry. Chrome needs no adaptation to serve a new site, and neither do we: the registry
    # stays a convenience for legacy seats, not a gate on new ones.
    if host in CHROME_CLIENTS or bool((raw or {}).get("chrome")):
        return ChromeReplayClient

    # Universal fallback for any provider with a recorded exchange blueprint
    if raw and (raw.get("recorded_exchange") or raw.get("recorded_job")):
        # A recorded_job IS a video capture (only record_video_job.py writes one), so it picks the
        # video client on its own -- the host-token list below is a convenience for files that were
        # stamped modality=video by hand, NOT a provider allowlist. Relying on the token list alone
        # meant a new provider whose name happens to lack a video word (pika.art, kling.ai, ...) got
        # the CHAT client: no job polling, and the submit's job-id JSON mis-parsed as an answer.
        video_job = bool(raw.get("recorded_job")) and not raw.get("recorded_exchange")
        if raw.get("modality") == "video" or video_job or any(
                vh in host for vh in ("video", "flow", "heygen", "akool", "creen", "digen", "veo")):
            from video_universal_replay import VideoUniversalSessionClient
            return VideoUniversalSessionClient
        from universal_replay import UniversalSessionClient
        return UniversalSessionClient
        
    return None


def _load_pool_state() -> Dict[str, float]:
    try:
        return json.loads(POOL_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Serializes state-file writes: the shim is a ThreadingHTTPServer, so concurrent successes used to
# call write_text() at the same moment -- last-writer-wins at best, a torn half-written file at
# worst (which would read back as {} and silently zero every cooldown). One lock + write-to-temp
# + os.replace makes every persisted snapshot atomic. (2026-08-27, worklog #1110)
_PERSIST_LOCK = threading.Lock()


def _save_pool_state(state: Dict[str, float]) -> None:
    try:
        with _PERSIST_LOCK:
            POOL_STATE.parent.mkdir(parents=True, exist_ok=True)
            tmp = POOL_STATE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            os.replace(tmp, POOL_STATE)         # atomic on NTFS -- readers never see a torn file
    except Exception:
        pass                                    # best-effort; cooldown still holds within a run


class PooledSession:
    """One grabbed session_<host>.json. Tracks routing bookkeeping only (host, liveness, last-used,
    cooldown) — the cookie/headers stay inside the replay client, never in this object's repr."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        # utf-8-sig: a hand-written hot-add seat file dropped from PowerShell/Notepad may
        # carry a BOM; tolerating it means the file still parses (worklog #1112).
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        try:
            self._file_mtime: Optional[float] = path.stat().st_mtime
        except OSError:
            self._file_mtime = None
        self.host: str = raw.get("host") or path.stem.replace("session_", "").replace("_", ".")
        self.key: str = path.stem                              # stable non-secret id for cooldown
        # Two capture shapes reach this pool as REPLAYABLE bytes: `recorded_exchange`
        # (capture_sessions_cdp.py, one-shot chat) and `recorded_job` (record_video_job.py, the
        # async submit->poll->result sequence). universal_replay._normalise_exchange accepts both.
        # NOTE (Doctrine 3a, CORRECTED 2026-08-28): `recorded_ws` (capture_websocket_cdp.py) is a
        # CHROME-BLUEPRINT capture, NOT replayable bytes — its runtime is the Chrome-blueprint
        # path (let the provider's own JS play by itself in a real V8 via Selenium), so it is
        # deliberately NOT counted here; ws seats stay dispatchable via has_chrome
        # (ChromeReplayClient) instead. Never hand-replay the provider's websocket protocol.
        # Testing only the chat key here made every freshly captured VIDEO seat non-dispatchable:
        # pool.live(modality="video") came back empty, the :8189 face answered 503 no_capacity
        # forever, and `list` blamed "no_recording" on a perfectly good capture.
        self.has_recording: bool = bool(raw.get("recorded_exchange") or raw.get("recorded_job"))
        # Chrome-backed seat (Adapter Thesis): the credential is the LIVE signed-in tab in
        # the operator's Chrome, not recorded bytes. Such a seat is dispatchable even with
        # no recording — ChromeReplayClient drives the provider's own UI. Its liveness is
        # "is the tab open", enforced at call time (NO_TAB -> failover), not here.
        # A seat may also DECLARE its Chrome backing inline ("chrome": {...} or true) with
        # zero registry entry -- the hot-add path (worklog #1112).
        self.has_chrome: bool = self.host in CHROME_CLIENTS or bool(raw.get("chrome"))
        # Chrome-doctrine VIDEO seat: the live tab's own UI generates the video. Dispatchable
        # even with no recording -- ChromeVideoClient drives the provider's own JS in-tab.
        # An inline "chrome" declaration is enough too (no VIDEO_HOSTS entry required).
        self.has_video_chrome: bool = (raw.get("modality") == "video"
                                       and (self.host in VIDEO_HOSTS
                                            or bool(raw.get("chrome"))))
        # A seat can also be usable WITHOUT a recording: an API-credential seat holds a bearer token
        # plus a documented contract (rtst.ai publishes quote/create/poll), so there is no genuine
        # exchange to replay and there never will be. Judging such a seat by has_recording alone made
        # it permanently non-dispatchable -- the pool reported no video capacity while sitting on real
        # credits. Same failure class as the two fixed in 7e2945b: the pool assumed every seat is a
        # replay seat.
        self.has_api: bool = bool(raw.get("api"))

        # record_video_job.py records ONLY video generations, so a recorded_job means video unless
        # the file explicitly says otherwise (a dual chat+video host keeps its declared modality).
        self.modality: str = raw.get("modality") or \
            ("video" if raw.get("recorded_job") and not raw.get("recorded_exchange") else "chat")
        status = raw.get("status") or {}
        # alive unless keepalive explicitly flagged it dead; a MISSING status = unknown-but-usable
        # (cookie/record verbs don't write status — only keepalive does).
        self.flagged_dead: bool = status.get("alive") is False
        self.reason: str = (status.get("reason") if status else None) or \
            ("no_recording" if not self.has_recording else "ok")
        self.runway_days = status.get("runway_days")
        ctx = raw.get("context") or {}
        self.logged_in = ctx.get("loggedIn")
        self.account_present = bool(ctx.get("userName"))
        self.client_cls = _client_for(self.host, raw)
        self._client = None
        self.last_used: float = 0.0
        self.cooldown_until: float = 0.0
        self.dead: bool = False                                # set this run on SessionExpired
        self.last_error: Optional[str] = None

    @property
    def dispatchable(self) -> bool:
        return bool((self.has_recording or self.has_api or self.has_chrome
                     or self.has_video_chrome) and self.client_cls
                    and not self.flagged_dead and not self.dead)

    def client(self):
        if self._client is None:
            self._client = self.client_cls(secret=self.path)
        return self._client

    def chat(self, messages, model=None, **kw) -> Dict[str, Any]:
        return self.client().chat(messages, model=model, **kw)


class SessionPool:
    """Least-recently-used router with per-session cooldown and per-host serialization."""

    def __init__(self, secrets: pathlib.Path = SECRETS, cooldown: float = DEFAULT_COOLDOWN):
        self.secrets = secrets
        self.cooldown = cooldown
        self._lock = threading.Lock()
        self._host_locks: Dict[str, threading.Lock] = {}
        self.sessions: List[PooledSession] = []
        for f in sorted(glob.glob(str(secrets / "session_*.json"))):
            try:
                self.sessions.append(PooledSession(pathlib.Path(f)))
            except Exception:
                continue                                       # skip corrupt/partial secret files
        st = _load_pool_state()
        for s in self.sessions:
            s.last_used = float(st.get(s.key, 0.0))

    def rescan(self) -> Dict[str, Any]:
        """Hot-reload the seat directory WITHOUT a restart (worklog #1112).

        One Chrome, infinite sites: adding a provider is dropping a seat file, nothing else.
        Re-globs session_*.json under the pool lock:
          * NEW files become live sessions (last_used restored from pool state),
          * vanished files are dropped,
          * CHANGED files (mtime moved) are re-parsed while carrying their runtime state
            (last_used / cooldown_until / dead) across,
          * untouched sessions keep their EXACT object -- including any instantiated
            client -- so a rescan never disturbs in-flight load spreading.
        Returns {"added": [...], "removed": [...], "changed": [...], "total": N}.
        """
        with self._lock:
            on_disk: Dict[str, pathlib.Path] = {}
            for f in sorted(glob.glob(str(self.secrets / "session_*.json"))):
                p = pathlib.Path(f)
                on_disk[p.stem] = p
            existing = {s.key: s for s in self.sessions}
            st = _load_pool_state()
            sessions: List[PooledSession] = []
            added: List[str] = []
            removed: List[str] = []
            changed: List[str] = []
            for key in sorted(on_disk):
                p = on_disk[key]
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                cur = existing.get(key)
                if cur is not None and getattr(cur, "_file_mtime", None) == mtime:
                    sessions.append(cur)                       # untouched: keep object+state
                    continue
                try:
                    s = PooledSession(p)
                except Exception:
                    if cur is not None:
                        sessions.append(cur)                   # unreadable update: keep old
                    continue
                if cur is not None:
                    s.last_used = cur.last_used                # file changed: rebuild but
                    s.cooldown_until = cur.cooldown_until      #   carry runtime state across
                    s.dead = cur.dead
                    s.last_error = cur.last_error
                    changed.append(key)
                else:
                    s.last_used = float(st.get(s.key, 0.0))
                    added.append(key)
                sessions.append(s)
            for key in existing:
                if key not in on_disk:
                    removed.append(key)
            self.sessions = sessions
            self._persist()
            return {"added": added, "removed": removed, "changed": changed,
                    "total": len(sessions)}

    def _host_lock(self, host: str) -> threading.Lock:
        with self._lock:
            if host not in self._host_locks:
                self._host_locks[host] = threading.Lock()
            return self._host_locks[host]

    def live(self, modality: Optional[str] = None, host: Optional[str] = None) -> List[PooledSession]:
        return [s for s in self.sessions if s.dispatchable
                and (modality is None or s.modality == modality)
                and (host is None or s.host == host)]

    def _persist(self) -> None:
        _save_pool_state({s.key: s.last_used for s in self.sessions if s.last_used})

    def pick(self, now: float, modality: Optional[str] = None, host: Optional[str] = None) -> Optional[PooledSession]:
        cands = [s for s in self.live(modality, host) if s.cooldown_until <= now]
        if not cands:
            return None
        cands.sort(key=lambda s: s.last_used)                  # least-recently-used first
        return cands[0]

    def reserve(self, modality: Optional[str] = None,
                host: Optional[str] = None) -> Optional[tuple]:
        """Atomically pick AND book the least-recently-used off-cooldown session.

        The old chat() called pick() OUTSIDE any lock: N concurrent consumers all read the same
        LRU head, then queued on the per-host lock and hammered ONE session in sequence -- the
        exact burst-on-one-provider the pool exists to prevent. Booking last_used + cooldown under
        self._lock makes every concurrent caller land on a DIFFERENT session, which is what turns
        the shim into a real parallel load spreader. Returns (session, reserved_at) or None.
        (2026-08-27, worklog #1110)
        """
        with self._lock:
            now = time.time()
            s = self.pick(now, modality, host)
            if s is None:
                return None
            s.last_used = now
            s.cooldown_until = now + self.cooldown
            return s, now

    def chat(self, messages, model=None, modality: Optional[str] = None,
             tries: Optional[int] = None, host: Optional[str] = None, **kw) -> Dict[str, Any]:
        """Route ONE call to the least-recently-used live session; on expiry/failure fall to the
        next. Never runs two concurrent calls to the same host (per-host lock)."""
        max_tries = tries if tries is not None else (len(self.live(modality, host)) or 1)
        attempted = 0
        last_exc: Optional[Exception] = None
        while attempted < max_tries:
            res = self.reserve(modality, host)                 # atomic pick+book (no double-book)
            if res is None:
                break
            s, res_at = res
            attempted += 1
            with self._host_lock(s.host):
                try:
                    r = s.chat(messages, model=model, **kw)
                    s.last_used = time.time()
                    s.cooldown_until = s.last_used + self.cooldown
                    self._persist()
                    r["provider"], r["session"] = s.host, s.key
                    return r
                except SessionExpired as e:
                    s.dead, s.last_error, last_exc = True, "session_expired", e
                    continue                                   # try the next provider
                except ChatError as e:
                    base = max(time.time(), res_at)
                    s.last_used = base
                    s.cooldown_until = base + max(self.cooldown, 30.0)
                    s.last_error, last_exc = str(e)[:60], e
                    continue
        if last_exc:
            raise last_exc
        raise ChatError("NO_LIVE_SESSION",
                        "no dispatchable session (all dead, cooling, or no proven adapter)")

    def sweep(self, prompt: str, model=None, workers: int = 6,
              modality: Optional[str] = None) -> List[Dict[str, Any]]:
        """One light call to EACH live session — the operator's 'ping each once' sweep. Distinct
        hosts run concurrently (spreading load, the whole point); sessions that share a host are
        serialized by the per-host lock so we never burst a single provider."""
        live = self.live(modality)
        results: List[Dict[str, Any]] = []
        rlock = threading.Lock()

        def one(s: PooledSession) -> None:
            t0 = time.time()
            with self._host_lock(s.host):
                try:
                    r = s.chat([{"role": "user", "content": prompt}], model=model)
                    s.last_used = time.time()
                    s.cooldown_until = s.last_used + self.cooldown
                    out = {"host": s.host, "session": s.key, "modality": s.modality, "ok": True,
                           "ms": int((time.time() - t0) * 1000), "label": r.get("label"),
                           "preview": (r.get("text") or "").replace("\n", " ")[:70]}
                except SessionExpired:
                    s.dead = True
                    out = {"host": s.host, "session": s.key, "modality": s.modality, "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "err": "session_expired (re-login + re-grab)"}
                except Exception as e:
                    out = {"host": s.host, "session": s.key, "modality": s.modality, "ok": False,
                           "ms": int((time.time() - t0) * 1000), "err": str(e)[:70]}
            with rlock:
                results.append(out)

        if live:
            with ThreadPoolExecutor(max_workers=max(1, min(workers, len(live)))) as ex:
                list(ex.map(one, live))
        self._persist()
        return results


def _cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--secrets", default=str(SECRETS))
    ap.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("chat")
    c.add_argument("prompt")
    c.add_argument("--model", default=None)
    c.add_argument("--modality", default=None)
    s = sub.add_parser("sweep")
    s.add_argument("--prompt", default="Reply with exactly one word: pong.")
    s.add_argument("--model", default=None)
    s.add_argument("--workers", type=int, default=6)
    s.add_argument("--modality", default=None, help="restrict to chat|video")

    a = ap.parse_args()
    pool = SessionPool(pathlib.Path(a.secrets), cooldown=a.cooldown)

    if a.cmd == "list":
        if not pool.sessions:
            print("(pool empty — no state/secrets/session_*.json yet; grab one with grab_session.py)")
            return 0
        print(f"{len(pool.sessions)} session file(s); {len(pool.live())} dispatchable:\n")
        for s in pool.sessions:
            adapter = "yes" if s.client_cls else "NO-ADAPTER"
            rw = "—" if s.runway_days is None else f"{s.runway_days}d"
            flag = "LIVE" if s.dispatchable else "OUT "
            print(f"  [{flag}] {s.host:26s} {s.modality:5s} adapter={adapter:10s} "
                  f"{'rec' if s.has_recording else 'no-rec':6s} "
                  f"logged_in={str(s.logged_in):5s} acct={str(s.account_present):5s} "
                  f"runway={rw:6s} reason={s.reason}")
        na = [s.host for s in pool.sessions if not s.client_cls]
        if na:
            print(f"\n  {len(na)} host(s) grabbed but awaiting a proven replay adapter: "
                  f"{', '.join(sorted(set(na)))}")
        return 0

    if a.cmd == "chat":
        r = pool.chat([{"role": "user", "content": a.prompt}], model=a.model, modality=a.modality)
        print(f'[{r.get("provider")} | {r.get("label")} | {r.get("frames")} frames]\n')
        print(r["text"])
        return 0

    if a.cmd == "sweep":
        res = pool.sweep(a.prompt, model=a.model, workers=a.workers, modality=a.modality)
        if not res:
            print("(no live sessions with a proven adapter to sweep yet)")
            return 0
        ok = 0
        for r in sorted(res, key=lambda x: x["host"]):
            if r["ok"]:
                ok += 1
                prev = str(r.get("preview", "")).encode("ascii", "replace").decode("ascii")[:80]
                print(f'  OK  {r["host"]:26s} {r["ms"]:6d}ms  {r.get("label",""):14s} {prev}')
            else:
                err = str(r.get("err", "")).encode("ascii", "replace").decode("ascii")[:80]
                print(f'  ERR {r["host"]:26s} {r["ms"]:6d}ms  {err}')
        print(f'\n{ok}/{len(res)} live sessions answered a single light call.')
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
