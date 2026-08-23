"""flow_shim.py -- serve Google Flow as a local video API, with multi-account rotation.

WHY THIS EXISTS (all facts below measured 2026-08-23)
-----------------------------------------------------
googleflow_client.py proved Flow's real RPC is drivable from Python end to end, with no human in
the loop: mint a reCAPTCHA Enterprise token in the live tab, POST the captured wire format, poll,
pull the MP4 with the tab's labs.google cookies. What it is NOT is something OmniRoute or a
filmmaking app can call.

OmniRoute cannot be pointed at Flow directly. Its compiled google-flow handler calls
/v1:generateVideo and /v1:fetchOperation; neither path exists on Flow's host, and both are baked
into a compiled chunk, so no credential or feature flag can redirect them. But OmniRoute's `comfyui`
video format is operator-steerable: its base URL comes from the credential's
providerSpecificData.baseUrl and defaults to http://localhost:8188, and it authenticates with
nothing (authType "none"). So a process that speaks ComfyUI's three-call contract on :8188 IS a
working Flow route through OmniRoute with zero OmniRoute code change.

This module serves TWO faces over the same job engine:

  :8189  the honest one -- POST /v1/videos/generations, GET the job, GET the MP4 bytes.
         Use this from the filmmaking app.
  :8188  the ComfyUI costume -- POST /prompt, GET /history/{id}, GET /view?filename=...
         Use this to make `comfyui/veo-3.1-fast` work as an OmniRoute model string.

THE COMFYUI CONTRACT, read off the compiled handler rather than guessed:
    POST {base}/prompt      {prompt: <workflow>}  -> {prompt_id}
    GET  {base}/history/{id}                      -> {} until done, then
                                                     {id: {outputs: {<node>: {gifs|images: [...]}}}}
                                                     polled every 2s for at most 300s
    GET  {base}/view?filename=&subfolder=&type=   -> the bytes
The workflow OmniRoute builds carries the prompt at node "2".inputs.text, the model at
"1".inputs.ckpt_name, geometry at "4".inputs.width/height and the seed at "5".inputs.seed.

TWO THINGS THE COMFYUI FACE CANNOT FIX, both inherited from the compiled handler:
  * it labels the response format "webp" no matter what the bytes are, so an MP4 arrives claiming
    to be a webp. The bytes are correct; the label lies.
  * its poller understands exactly two outcomes, "outputs appeared" and "300s elapsed". There is no
    error channel, so a Flow failure reaches OmniRoute as a timeout ~300s later. The direct face
    reports the same failure in seconds, which is why the filmmaking app should use the direct face.

WHY A BROWSER MUST STAY RUNNING: the bearer is a web session token read from
labs.google/fx/api/auth/session, and the reCAPTCHA token can only be minted by Google's own JS
inside a real page. Neither has a server-side equivalent. The Chrome windows can be minimised and
unfocused and nobody has to click anything -- but they must be alive, one per account, each with its
own --remote-debugging-port, because Flow auth is a single NextAuth cookie per profile.

SAFETY PROPERTIES THIS FILE IS RESPONSIBLE FOR
  * assert_cdp_safe() on every account port, so a profile misconfigured onto the operator's live
    Chrome is refused rather than risking the session revocation described in chrome_live_guard.py.
  * one lock per account held across submit+poll, so two jobs can never race the same balance.
  * binds to 127.0.0.1 by default; a non-loopback bind REQUIRES --token, because this process
    spends real money.
  * bearer tokens, captcha tokens and cookies stay in memory, are never logged and never persisted;
    every error string goes through scrub() before it is logged or returned.

    python flow_shim.py doctor            # which link in the chain is broken, and what to do
    python flow_shim.py accounts          # registry + live balances
    python flow_shim.py serve             # run both faces
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import googleflow_client as gf  # noqa: E402
from cdp import DEFAULT_PORT, Page, list_targets  # noqa: E402

try:
    from chrome_live_guard import assert_cdp_safe, is_refusal
except Exception:  # pragma: no cover -- guard is present in this repo; degrade loudly, not silently
    def assert_cdp_safe(endpoint, who="flow_shim"):
        print("!! chrome_live_guard not importable -- live-profile protection is OFF")
        return endpoint

    def is_refusal(exc):
        return False

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
ACCOUNTS_FILE = STATE / "flow_accounts.json"
JOBS_FILE = STATE / "flow_jobs.jsonl"

DIRECT_PORT = 8189
COMFY_PORT = 8188            # OmniRoute's built-in default for the comfyui video provider

# OmniRoute's compiled comfyui poller gives up after exactly 300s (3e5 ms) and has no error channel.
# Anything the ComfyUI face starts that cannot finish inside that window charges credits for a video
# OmniRoute will never collect, so every comfy-face deadline is derived from this number instead of
# from the direct face's much more generous defaults.
OMNIROUTE_COMFY_WINDOW = 300
COMFY_ACQUIRE_TIMEOUT = 20   # no account free almost immediately -> fail BEFORE spending anything
COMFY_BUDGET = 230           # leaves room for submit, download and OmniRoute's 2s poll cadence

# cdp.pick_page signals "no matching tab" by raising SystemExit, which `except Exception` does not
# catch. Uncaught in a worker thread it abandons a job whose credits are already spent; uncaught in
# the refresh loop it freezes every balance for the life of the process. A missing tab is a routine,
# recoverable condition here, so it is caught everywhere a browser is touched.
NON_FATAL = (Exception, SystemExit)

# Flow's own model keys. Only the fast key has actually been exercised end to end; the other two
# follow its naming pattern and are marked so a caller is never told an inference is a measurement.
PROVEN_MODEL_KEYS = {"veo_3_1_t2v_fast"}

MODEL_ALIASES = {
    "fast": "veo_3_1_t2v_fast",
    "veo-3.1-fast": "veo_3_1_t2v_fast",
    "veo3.1-fast": "veo_3_1_t2v_fast",
    "veo-3.1-fast-generate": "veo_3_1_t2v_fast",
    "animatediff": "veo_3_1_t2v_fast",       # OmniRoute's registered comfyui model id
    "quality": "veo_3_1_t2v_quality",
    "veo-3.1": "veo_3_1_t2v_quality",
    "veo-3.1-quality": "veo_3_1_t2v_quality",
    "veo-3.1-generate": "veo_3_1_t2v_quality",
    "svd-xt": "veo_3_1_t2v_quality",         # the other registered comfyui model id
    "lite": "veo_3_1_t2v_lite",
    "veo-3.1-lite": "veo_3_1_t2v_lite",
}

# One 720p/8s fast clip charged 60 from here, against 20 for the same parameters clicked in the UI.
# Unexplained, so this is only a floor for "does the account have enough" and every job overwrites it
# with what was actually charged.
EST_COST = 60
MEASURED_COST: dict[str, int] = {}

MEDIA_ID_RE = re.compile(r"^[0-9A-Za-z_\-]{6,80}$")
FLOW_MATCH = "tools/flow"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {gf.scrub(msg)}", flush=True)


def resolve_model(name: str | None) -> str | None:
    """Loose name -> Flow model key. Unknown names are rejected rather than silently defaulted:
    quietly generating a fast clip for someone who asked for quality is a billing surprise."""
    if not name:
        return "veo_3_1_t2v_fast"
    n = str(name).strip().lower()
    if n.startswith("veo_"):
        return n                       # already a Flow key, pass through untouched
    if "/" in n:                       # tolerate a full OmniRoute model string
        n = n.rsplit("/", 1)[1]
    return MODEL_ALIASES.get(n)


def geometry(width: int | None, height: int | None) -> tuple[str, str]:
    """ComfyUI speaks pixels; Flow speaks two enums. Square (OmniRoute's 512x512 default) has no
    Flow equivalent, so it lands on landscape 720p."""
    if not width or not height:
        return "16:9", "720p"
    aspect = "9:16" if height > width else "16:9"
    res = "1080p" if (max(width, height) >= 1920 or min(width, height) >= 1080) else "720p"
    return aspect, res


# --------------------------------------------------------------------------- accounts


class Account:
    """One Google account == one Chrome profile == one debugging port."""

    def __init__(self, port: int, label: str = "", enabled: bool = True):
        self.port = int(port)
        self.label = label or f"port-{port}"
        self.enabled = bool(enabled)
        self.lock = threading.Lock()
        self.email: str | None = None
        self.project_id: str | None = None
        self.tier: str | None = None
        self.credits: int | None = None
        self.ready = False
        self.reason = "not probed yet"
        self._sess: gf.FlowSession | None = None
        self._sess_at = 0.0

    def public(self, redact: bool = False) -> dict:
        """redact=True is the pre-authentication shape: enough to see the fleet is alive, nothing
        that identifies an account. Emails, project ids, tiers, balances and the free-text `reason`
        (which can quote an upstream error verbatim) are withheld until the caller authenticates."""
        d = {"label": self.label, "port": self.port, "enabled": self.enabled,
             "ready": self.ready, "busy": self.lock.locked()}
        if redact:
            return d
        d.update(email=self.email, project_id=self.project_id, tier=self.tier,
                 credits=self.credits, reason=self.reason)
        return d


class Fleet:
    """The set of accounts, their live balances, and the rule for choosing one."""

    SESSION_TTL = 600          # bearer is good ~12h; re-reading every 10min is cheap insurance
    REFRESH_EVERY = 90

    def __init__(self, accounts: list[Account]):
        self.accounts = accounts
        self._select = threading.Lock()
        self._stop = threading.Event()

    # -- session handling, with the one self-heal that matters ------------------------------

    def session(self, acct: Account, force: bool = False) -> gf.FlowSession:
        """A live FlowSession for this account, cached briefly.

        The single failure this heals: after the machine sleeps or the tab sits idle for hours,
        /fx/api/auth/session can answer without an access_token until the page is reloaded. That is
        a page-state problem, not a credential problem, so one reload is tried before giving up.
        """
        if (not force and acct._sess is not None
                and (time.time() - acct._sess_at) < self.SESSION_TTL):
            return acct._sess

        assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who=f"flow_shim account {acct.label}")
        try:
            sess = gf.FlowSession(FLOW_MATCH, port=acct.port).refresh()
        except NON_FATAL as first:
            if "session token" not in str(first):
                raise
            log(f"{acct.label}: no access_token, reloading the Flow tab once")
            self._reload(acct)
            sess = gf.FlowSession(FLOW_MATCH, port=acct.port).refresh()

        acct._sess, acct._sess_at = sess, time.time()
        acct.email, acct.project_id, acct.tier = sess.email, sess.project_id, sess.tier
        return sess

    def _reload(self, acct: Account) -> None:
        try:
            with Page(FLOW_MATCH, port=acct.port) as p:
                p.send("Page.reload", {}, timeout=60)
                for _ in range(30):
                    time.sleep(1)
                    try:
                        if p.evaluate("document.readyState", timeout=15) == "complete":
                            break
                    except NON_FATAL:
                        continue
            time.sleep(3)
        except NON_FATAL as e:
            log(f"{acct.label}: reload failed: {type(e).__name__}: {e}")

    # -- balances ---------------------------------------------------------------------------

    def probe(self, acct: Account) -> None:
        """Refresh one account's readiness and balance. Never raises: an account being down is a
        state to report and route around, not an error that takes the server with it."""
        try:
            sess = self.session(acct)
            if not sess.project_id:
                acct.ready, acct.reason = False, "tab is not inside a Flow /project/ URL"
                return
            c = gf.credits_now(sess)
            if c is None:
                acct.ready, acct.reason = False, "credits endpoint did not answer 200"
                return
            acct.credits, acct.ready, acct.reason = c, True, "ok"
        except NON_FATAL as e:
            if is_refusal(e):
                acct.enabled = False
                acct.ready, acct.reason = False, "REFUSED: points at the operator's live Chrome"
                log(f"{acct.label}: {acct.reason} -- disabled")
                return
            acct.ready = False
            acct.reason = f"{type(e).__name__}: {gf.scrub(str(e))[:160]}"

    def probe_all(self, parallel: bool = True) -> None:
        """Probe every idle account. Accounts mid-generation are skipped, not waited for: probing
        can reload the Flow tab (see session()), and doing that underneath a job whose credits are
        already spent destroys the generation. A skipped account keeps its last known balance, which
        is correct anyway -- it is busy, so the rotation would not pick it.
        """
        targets = [a for a in self.accounts if a.enabled and a.lock.acquire(blocking=False)]
        try:
            if not parallel:
                for a in targets:
                    self.probe(a)
                return
            ts = [threading.Thread(target=self.probe, args=(a,), daemon=True) for a in targets]
            [t.start() for t in ts]
            [t.join(timeout=120) for t in ts]
        finally:
            for a in targets:
                try:
                    a.lock.release()
                except RuntimeError:
                    pass

    def refresh_loop(self) -> None:
        """Never allowed to die. A dead refresh loop freezes every balance at its last value and the
        rotation then routes on stale numbers -- including routing to an account that no longer has
        the credits for the job."""
        while not self._stop.wait(self.REFRESH_EVERY):
            try:
                self.probe_all()
            except NON_FATAL as e:
                log(f"refresh loop: {type(e).__name__}: {gf.scrub(str(e))[:120]} -- continuing")

    # -- the rotation rule ------------------------------------------------------------------

    def acquire(self, need: int, requested: str | None = None,
                timeout: float = 900) -> Account:
        """Reserve an account, holding its lock. Caller MUST release it.

        Highest balance first, so the fleet drains evenly rather than burning one account to zero
        while three sit full. The lock is held across submit AND poll: that is what makes the
        credits-before/after delta trustworthy and makes double-spend structurally impossible.
        """
        deadline = time.time() + timeout
        first_pass = True
        while time.time() < deadline:
            with self._select:
                pool = [a for a in self.accounts if a.enabled]
                if requested:
                    r = str(requested).strip().lower()
                    if r not in ("", "auto", "any"):
                        pool = [a for a in pool
                                if r in (str(a.port), a.label.lower(), (a.email or "").lower())]
                        if not pool:
                            raise RuntimeError(f"no account matches {requested!r}")
                if first_pass and not any(a.ready for a in pool):
                    self.probe_all()
                    first_pass = False
                ranked = sorted((a for a in pool if a.ready and (a.credits or 0) >= need),
                                key=lambda a: -(a.credits or 0))
                for acct in ranked:
                    if acct.lock.acquire(blocking=False):
                        return acct
                if pool and not any(a.ready for a in pool):
                    raise RuntimeError("no account is ready: "
                                       + "; ".join(f"{a.label}: {a.reason}" for a in pool))
                if pool and not any((a.credits or 0) >= need for a in pool if a.ready):
                    raise RuntimeError(
                        f"no account has the ~{need} credits this needs: "
                        + "; ".join(f"{a.label}={a.credits}" for a in pool if a.ready))
            time.sleep(2)
        raise RuntimeError(f"every account stayed busy for {timeout:.0f}s")


def load_accounts() -> Fleet:
    if not ACCOUNTS_FILE.exists():
        STATE.mkdir(parents=True, exist_ok=True)
        ACCOUNTS_FILE.write_text(json.dumps({
            "_note": "One entry per Google account. Each needs its OWN Chrome profile with its own "
                     "--remote-debugging-port, parked on a labs.google Flow /project/ URL. "
                     "Never point one at the operator's live Chrome profile.",
            "accounts": [{"label": "pro-1", "port": DEFAULT_PORT, "enabled": True}],
        }, indent=2), encoding="utf-8")
        log(f"wrote a starter registry at {ACCOUNTS_FILE}")
    raw = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    accts = [Account(a["port"], a.get("label", ""), a.get("enabled", True))
             for a in raw.get("accounts", [])]
    if not accts:
        raise SystemExit(f"no accounts in {ACCOUNTS_FILE}")
    return Fleet(accts)


# --------------------------------------------------------------------------- jobs


def _snap(job: dict) -> dict:
    """A shallow copy safe to serialise while the worker thread is still writing to the original.
    Lists are copied too, because json.dumps walks them. Every key a job will ever have is created
    up front in JobStore.create, so this iteration can never see the dict change size."""
    return {k: (list(v) if isinstance(v, list) else v) for k, v in job.items()}


class JobStore:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Replay the append-only log so a restart does not orphan finished videos.

        Anything the log still calls queued/active was in flight when the process died. Its thread is
        gone, so it can never progress: left as-is, a caller polls that job id forever. It is marked
        `interrupted` instead, and kept rather than dropped -- Flow may well have charged for it, so
        the record is the only trace of where the credits went.
        """
        if not JOBS_FILE.exists():
            return
        try:
            for line in JOBS_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    self.jobs[j["id"]] = j
        except Exception as e:
            log(f"job log unreadable ({type(e).__name__}) -- starting empty")
        stale = [j for j in self.jobs.values() if j.get("status") in ("queued", "active")]
        for j in stale:
            j["status"] = "interrupted"
            j["error"] = ("the shim restarted while this job was in flight; credits may already have "
                          "been charged -- check the balance and state/harvest/flow/ before retrying")
            j["finished"] = time.time()
        if stale:
            log(f"{len(stale)} job(s) were in flight at the last shutdown -> marked interrupted")
            for j in stale:
                log(f"  {j['id'][:8]} {j.get('model')} media={j.get('media_id')} "
                    f"charged={j.get('credits_charged')}")

    def create(self, **fields) -> dict:
        job = {"id": uuid.uuid4().hex, "status": "queued", "created": time.time(),
               "finished": None, "project_id": None, "dry_run": False,
               "account": None, "port": None, "media_id": None, "media_ids": [], "error": None,
               "credits_before": None, "credits_after": None, "credits_charged": None,
               "media_count": None, "workflow_count": None, "flow_status": None,
               "duration": None, "durations": [], "bytes": None, "bytes_each": [],
               "bytes_total": None, "file": None, "files": [], **fields}
        with self.lock:
            self.jobs[job["id"]] = job
        self.persist(job)
        return job

    def persist(self, job: dict) -> None:
        try:
            JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with JOBS_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(_snap(job), default=str) + "\n")
        except Exception:
            pass                      # a job log that cannot be written must not fail the job

    # Readers hand out snapshots, never the live dict. run_job mutates its job from a worker thread
    # while HTTP threads serialise it; json.dumps over a dict or list that is being mutated raises
    # "changed size during iteration" and kills the response mid-flight.
    def get(self, jid: str) -> dict | None:
        with self.lock:
            j = self.jobs.get(jid)
            return _snap(j) if j else None

    def by_media(self, media_id: str) -> dict | None:
        with self.lock:
            for j in self.jobs.values():
                if j.get("media_id") == media_id or media_id in (j.get("media_ids") or []):
                    return _snap(j)
        return None

    def recent(self, n: int = 50) -> list[dict]:
        with self.lock:
            newest = sorted(self.jobs.values(), key=lambda j: j.get("created", 0),
                            reverse=True)[:n]
            return [_snap(j) for j in newest]

    def stats(self) -> dict:
        with self.lock:
            vals = list(self.jobs.values())
        return {"total": len(vals),
                "active": sum(1 for j in vals if j.get("status") in ("queued", "active"))}


FLEET: Fleet
STORE = JobStore()

# Set by `serve --dry-run`. A dry run exercises every byte of both HTTP contracts -- OmniRoute's
# poller, the base64 envelope, the filmmaking app's client -- without touching Flow, so the plumbing
# can be regression-tested for free instead of at 60 credits a go. It is surfaced in /healthz and on
# every job so a dry run can never be mistaken for a real one.
DRY_RUN = False


def _dry_media() -> str | None:
    """The newest already-downloaded clip, reused as stand-in bytes for a dry run."""
    try:
        files = sorted(gf.OUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0].stem if files else None
    except Exception:
        return None


def run_job(job: dict) -> None:
    """Submit, poll, download. Owns one account for its whole life."""
    if DRY_RUN:
        job["dry_run"] = True
        job["status"] = "active"
        job["account"] = "(dry run -- no account used)"
        time.sleep(4)
        mid = _dry_media()
        if not mid:
            job["status"] = "failed"
            job["error"] = ("dry run has no cached mp4 to serve; run one real generation first "
                            "or drop --dry-run")
        else:
            f = gf.OUT_DIR / f"{mid}.mp4"
            job.update(status="succeeded", media_id=mid, media_ids=[mid], file=str(f),
                       files=[str(f)], bytes=f.stat().st_size, bytes_each=[f.stat().st_size],
                       bytes_total=f.stat().st_size, credits_charged=0, duration="8s",
                       durations=["8s"], flow_status="SUCCESSFUL (simulated)",
                       media_count=1, workflow_count=1)
        job["finished"] = time.time()
        log(f"{job['id'][:8]} DRY RUN {job['status']} -> {job.get('media_id')}")
        STORE.persist(job)
        return

    need = MEASURED_COST.get(job["model"], EST_COST)
    acct = None
    try:
        acct = FLEET.acquire(need, job.get("requested_account"),
                             timeout=float(job.get("acquire_timeout") or 900))
        job["account"], job["port"] = acct.email or acct.label, acct.port
        job["status"] = "active"
        sess = FLEET.session(acct)
        job["project_id"] = sess.project_id

        job["credits_before"] = gf.credits_now(sess)
        log(f"{job['id'][:8]} -> {acct.label} ({job['model']}, {job['resolution']} {job['aspect']})")

        r = gf.submit(sess, job["prompt"], model=job["model"], resolution=job["resolution"],
                      aspect=job["aspect"], seed=job.get("seed"))
        media = r.get("media") or []
        job["media_count"] = len(media)
        job["workflow_count"] = len(r.get("workflows") or [])
        # Flow answers one submit with a LIST of medias and bills for all of them. Taking media[0]
        # and dropping the rest is what a 60-credit charge for one 20-credit clip looks like: every
        # id here is already paid for, so every id here gets polled and downloaded.
        ids = [m.get("name") for m in media
               if isinstance(m, dict) and isinstance(m.get("name"), str) and m.get("name")]
        job["media_ids"] = ids
        job["media_id"] = ids[0] if ids else None
        job["credits_after"] = r.get("remainingCredits")
        if isinstance(job["credits_before"], int) and isinstance(job["credits_after"], int):
            job["credits_charged"] = job["credits_before"] - job["credits_after"]
            if job["credits_charged"] > 0:
                MEASURED_COST[job["model"]] = job["credits_charged"]
        if isinstance(job["credits_after"], int):
            acct.credits = job["credits_after"]
        if not ids:
            raise RuntimeError("submit returned no media id")
        # The 60-vs-20 question: if Flow billed three clips, this is where it shows.
        log(f"{job['id'][:8]} submitted {len(ids)} media ({', '.join(i[:12] for i in ids)})  "
            f"workflows={job['workflow_count']} charged={job['credits_charged']}")
        STORE.persist(job)

        # One shared deadline across all medias, not `budget` each: Flow renders them concurrently,
        # and a per-media budget would let a 3-media job run 3x longer than the caller asked for --
        # which for the comfy face means blowing straight through OmniRoute's 300s window.
        deadline = time.time() + float(job.get("budget") or 600)
        files: list[str] = []
        sizes: list[int] = []
        durations: list = []
        for n, mid in enumerate(ids, 1):
            def on_status(st, elapsed, _n=n, _mid=mid):
                job["flow_status"] = f"[{_n}/{len(ids)}] {st}"
                log(f"{job['id'][:8]} [{_n}/{len(ids)}] {st} at {elapsed:.0f}s")

            left = deadline - time.time()
            if left < 10:
                raise RuntimeError(
                    f"budget exhausted after {n - 1}/{len(ids)} media; {len(ids) - n + 1} paid "
                    f"clip(s) not collected -- ids are recorded, fetch them with "
                    f"`googleflow_client.py fetch <id>`: {', '.join(ids[n - 1:])}")
            m = gf.wait(sess, mid, budget=int(left), on_status=on_status)
            durations = durations + [m.get("video", {}).get("dimensions", {}).get("length")]
            dest = gf.download(mid, port=acct.port, verbose=False)
            files = files + [str(dest)]
            sizes = sizes + [dest.stat().st_size]
            # Reassigned, never appended in place: an HTTP thread may be snapshotting these lists.
            job["files"], job["bytes_each"], job["durations"] = files, sizes, durations
            job["file"], job["bytes"] = files[0], sizes[0]
            job["duration"] = durations[0]
            job["bytes_total"] = sum(sizes)
            STORE.persist(job)

        job["status"] = "succeeded"
        job["finished"] = time.time()
        log(f"{job['id'][:8]} done in {job['finished'] - job['created']:.0f}s  "
            f"{len(files)} file(s) {job['bytes_total']} bytes -> "
            f"{', '.join(pathlib.Path(f).name for f in files)}")
    except NON_FATAL as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {gf.scrub(str(e))[:400]}"
        job["finished"] = time.time()
        log(f"{job['id'][:8]} FAILED {job['error']}")
        if job.get("media_ids") and not job.get("files"):
            log(f"{job['id'][:8]} WARNING: credits were already charged for "
                f"{len(job['media_ids'])} media; nothing was downloaded")
        if job.get("face") == "comfyui":
            log(f"{job['id'][:8]} note: the ComfyUI face has no error channel, so OmniRoute will "
                f"report this as a timeout ~300s from its submit")
    finally:
        if acct is not None:
            try:
                acct.lock.release()
            except RuntimeError:
                pass
        STORE.persist(job)


def start_job(*, prompt: str, model_name: str | None, aspect: str, resolution: str,
              seed: int | None, requested_account: str | None, face: str,
              budget: int = 600, acquire_timeout: float = 900) -> tuple[dict | None, str | None]:
    if not prompt or not str(prompt).strip():
        return None, "prompt is required and cannot be empty"
    key = resolve_model(model_name)
    if not key:
        return None, (f"unknown model {model_name!r}; try one of: "
                      + ", ".join(sorted(set(MODEL_ALIASES))))
    job = STORE.create(prompt=str(prompt), model=key, aspect=aspect, resolution=resolution,
                       seed=seed, requested_account=requested_account, face=face, budget=budget,
                       acquire_timeout=acquire_timeout,
                       model_key_proven=key in PROVEN_MODEL_KEYS)
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job, None


def public_job(job: dict) -> dict:
    out = {k: v for k, v in job.items() if not k.startswith("_")}
    if job.get("status") == "succeeded":
        out["content_url"] = f"/v1/videos/{job['id']}/content"
        out["content_urls"] = [f"/v1/videos/{job['id']}/content?index={i}"
                               for i in range(len(job.get("files") or []))]
    return out


# --------------------------------------------------------------------------- http plumbing


class Base(BaseHTTPRequestHandler):
    server_version = "FlowShim/1.0"
    token: str | None = None
    # StreamRequestHandler applies this to the connection socket. Without it a client that opens a
    # socket, announces a Content-Length and then stops sending pins a worker thread forever.
    timeout = 60
    # A ComfyUI workflow is a few KB. Reading an arbitrary client-declared length into memory on a
    # process that is meant to sit on localhost forever is not worth the generality.
    MAX_BODY = 1 << 20

    def log_message(self, fmt, *args):        # quieter than the stdlib default, and scrubbed
        log(f"{self.address_string()} {gf.scrub(fmt % args)}")

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, indent=1, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str) -> None:
        self._json(code, {"error": {"code": code, "message": gf.scrub(msg)}})

    def _body(self) -> dict | None:
        """None means "reject this request". A JSON body that is valid but not an object counts:
        callers go straight to .get() on the result, so a bare list or string would raise inside the
        handler and the client would get a dropped connection instead of a 400."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0:
            return {}
        if n > self.MAX_BODY:
            return None
        try:
            obj = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None

    def _authed(self) -> bool:
        if not self.token:
            return True
        got = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        return got == self.token

    def _send_video(self, path: pathlib.Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _resolve_media_file(self, ident: str, index: int = 0) -> pathlib.Path | None:
        """A job id, or a media id, or a media id with .mp4 on it -> the file on disk.

        A job can own several medias (Flow bills for all of them), so a job id plus an index selects
        one of them; a media id addresses itself and ignores the index.
        """
        ident = ident.strip()
        job = STORE.get(ident)
        media_id = None
        if job:
            ids = job.get("media_ids") or ([job["media_id"]] if job.get("media_id") else [])
            if 0 <= index < len(ids):
                media_id = ids[index]
        if not media_id:
            media_id = ident[:-4] if ident.endswith(".mp4") else ident
        if not media_id or not MEDIA_ID_RE.match(media_id):
            return None
        p = gf.OUT_DIR / f"{media_id}.mp4"
        # Belt and braces against a crafted id escaping the harvest directory.
        try:
            p.resolve().relative_to(gf.OUT_DIR.resolve())
        except ValueError:
            return None
        return p if p.exists() else None


# --------------------------------------------------------------------------- direct face


class DirectHandler(Base):
    """The face the filmmaking app should use. Honest content types, honest errors."""

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path.rstrip("/") or "/", urllib.parse.parse_qs(u.query)
        if path in ("/", "/healthz"):
            # Reachable without a token so a liveness probe keeps working, but only in redacted form:
            # the full shape carries account emails, project ids, balances and upstream error text.
            authed = self._authed()
            return self._json(200, {
                "ok": DRY_RUN or any(a.ready for a in FLEET.accounts),
                "dry_run": DRY_RUN,
                "authenticated": authed,
                "accounts": [a.public(redact=not authed) for a in FLEET.accounts],
                "jobs": STORE.stats(),
                "measured_cost": (MEASURED_COST or {"(none yet)": EST_COST}) if authed else None,
            })
        if not self._authed():
            return self._err(401, "bad or missing bearer token")
        if path == "/v1/accounts":
            if q.get("refresh"):
                FLEET.probe_all()
            return self._json(200, {"accounts": [a.public() for a in FLEET.accounts]})
        if path == "/v1/models":
            return self._json(200, {"data": [
                {"id": k, "flow_key": v, "proven": v in PROVEN_MODEL_KEYS,
                 "length_seconds": 8, "note": None if v in PROVEN_MODEL_KEYS
                 else "model key inferred from the fast key's naming, never exercised"}
                for k, v in sorted(MODEL_ALIASES.items())]})
        if path == "/v1/videos/generations":
            return self._json(200, {"data": [public_job(j) for j in STORE.recent()]})
        m = re.match(r"^/v1/videos/generations/([0-9a-f]{32})$", path)
        if m:
            job = STORE.get(m.group(1))
            return self._json(200, public_job(job)) if job else self._err(404, "no such job")
        m = re.match(r"^/v1/videos/([^/]+)/content$", path)
        if m:
            try:
                idx = int((q.get("index") or ["0"])[0])
            except ValueError:
                return self._err(400, "index must be an integer")
            f = self._resolve_media_file(urllib.parse.unquote(m.group(1)), index=idx)
            if not f:
                return self._err(404, "no bytes for that id (still running, failed, or unknown)")
            return self._send_video(f)
        return self._err(404, f"no route for {path}")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if (u.path.rstrip("/") or "/") != "/v1/videos/generations":
            return self._err(404, f"no route for {u.path}")
        if not self._authed():
            return self._err(401, "bad or missing bearer token")
        b = self._body()
        if b is None:
            return self._err(400, "body must be a JSON object under 1 MiB")

        aspect, resolution = b.get("aspect_ratio"), b.get("resolution")
        if b.get("size") and not (aspect and resolution):
            try:
                w, h = (int(x) for x in str(b["size"]).lower().split("x"))
                aspect, resolution = geometry(w, h)
            except Exception:
                return self._err(400, "size must look like 1280x720")
        aspect = aspect or "16:9"
        resolution = resolution or "720p"
        if aspect not in gf.ASPECTS:
            return self._err(400, f"aspect_ratio must be one of {list(gf.ASPECTS)}")
        if resolution not in gf.RESOLUTIONS:
            return self._err(400, f"resolution must be one of {list(gf.RESOLUTIONS)}")

        # Every number is parsed BEFORE start_job. Parsing them after it means a typo in wait_timeout
        # raises inside the handler while the worker thread is already spending credits, and the
        # caller never even learns the job id.
        def num(field, default, lo, hi, cast=int):
            raw = b.get(field)
            if raw is None or raw == "":
                return default, None
            try:
                v = cast(raw)
            except (TypeError, ValueError):
                return None, f"{field} must be a number"
            if not (lo <= v <= hi):
                return None, f"{field} must be between {lo} and {hi}"
            return v, None

        seed, err = num("seed", None, 0, 2 ** 32 - 1)
        if err:
            return self._err(400, err)
        budget, err = num("budget", 600, 30, 3600)
        if err:
            return self._err(400, err)
        wait_timeout, err = num("wait_timeout", 600, 1, 3600, float)
        if err:
            return self._err(400, err)

        job, err = start_job(prompt=b.get("prompt"), model_name=b.get("model"), aspect=aspect,
                             resolution=resolution, seed=seed,
                             requested_account=b.get("account"), face="direct", budget=budget)
        if err:
            return self._err(400, err)

        if b.get("wait"):
            limit = time.time() + wait_timeout
            while time.time() < limit and job["status"] in ("queued", "active"):
                time.sleep(0.5)
            return self._json(200, public_job(STORE.get(job["id"]) or job))
        return self._json(202, public_job(STORE.get(job["id"]) or job))


# --------------------------------------------------------------------------- comfyui face


class ComfyHandler(Base):
    """ComfyUI's contract, exactly as OmniRoute's compiled handler consumes it.

    Bound to loopback unconditionally (see serve()): this face is unauthenticated because
    OmniRoute's comfyui provider is authType "none", and POST /prompt spends real credits.
    """

    OUTPUT_NODE = "7"        # the SaveAnimatedWEBP node in OmniRoute's generated workflow

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path.rstrip("/") or "/", urllib.parse.parse_qs(u.query)

        if path == "/view":
            fn = (q.get("filename") or [""])[0]
            f = self._resolve_media_file(urllib.parse.unquote(fn))
            if not f:
                return self._err(404, "unknown filename")
            return self._send_video(f)

        m = re.match(r"^/history/([0-9a-f]{32})$", path)
        if m:
            job = STORE.get(m.group(1))
            if not job:
                return self._json(200, {})
            files = job.get("files") or ([job["file"]] if job.get("file") else [])
            if job["status"] == "succeeded" and files:
                return self._json(200, {job["id"]: {
                    "status": {"status_str": "success", "completed": True, "messages": []},
                    "outputs": {self.OUTPUT_NODE: {"gifs": [
                        {"filename": pathlib.Path(f).name, "subfolder": "", "type": "output",
                         "format": "video/mp4"} for f in files]}}}})
            if job["status"] in ("failed", "interrupted"):
                # Real ComfyUI's error shape. OmniRoute's poller ignores `status` and only looks for
                # `outputs`, so it will keep polling until its own 300s budget expires -- there is no
                # error channel in that contract. Anything that reads ComfyUI properly sees this.
                return self._json(200, {job["id"]: {
                    "status": {"status_str": "error", "completed": False,
                               "messages": [["execution_error", {"exception_message":
                                                                 job.get("error") or "failed"}]]},
                    "outputs": {}}})
            return self._json(200, {})            # queued/active: not done yet
        if path == "/history":
            return self._json(200, {})
        if path == "/system_stats":
            return self._json(200, {"system": {"comfyui_version": "flow-shim",
                                               "python_version": sys.version.split()[0]},
                                    "devices": []})
        if path == "/queue":
            # Counts, not ids. A job id here is a capability: it opens /history/{id}, which names the
            # media file, which /view then hands over as bytes the operator paid for.
            st = STORE.stats()
            return self._json(200, {"queue_running": [], "queue_pending": [],
                                    "flow_shim": {"running": st["active"], "total": st["total"],
                                                  "note": "ids withheld; use the :8189 face"}})
        return self._err(404, f"no route for {path}")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        if path == "/interrupt":
            return self._json(200, {})
        if path != "/prompt":
            return self._err(404, f"no route for {path}")
        b = self._body()
        if b is None:
            return self._err(400, "body must be a JSON object under 1 MiB")
        wf = b.get("prompt")
        if not isinstance(wf, dict):
            return self._err(400, "body must be {\"prompt\": <workflow>}")

        # Pull the interesting fields out of OmniRoute's generated workflow by CLASS rather than by
        # node number, so a handler change that renumbers nodes does not silently send an empty
        # prompt to a paid API.
        def by_class(cls):
            return {k: n for k, n in wf.items()
                    if isinstance(n, dict) and n.get("class_type") == cls}

        ckpt = next((n.get("inputs", {}).get("ckpt_name")
                     for n in by_class("CheckpointLoaderSimple").values()), None)
        latent = next((n.get("inputs", {}) for n in by_class("EmptyLatentImage").values()), {})
        sampler = next((n.get("inputs", {}) for n in by_class("KSampler").values()), {})

        # The positive and negative prompts are BOTH CLIPTextEncode nodes, so "first non-empty text"
        # picks the negative prompt whenever the positive one is blank -- i.e. it would pay to render
        # "blurry, low quality, distorted". The only thing that distinguishes them is which KSampler
        # input links to them, so follow that link. ComfyUI links are [node_id, output_index].
        encoders = by_class("CLIPTextEncode")

        def text_via(role):
            link = sampler.get(role)
            if isinstance(link, list) and link and str(link[0]) in encoders:
                t = encoders[str(link[0])].get("inputs", {}).get("text")
                return t if isinstance(t, str) else None
            return None

        prompt = text_via("positive")
        if prompt is None and len(encoders) == 1:
            # No KSampler to disambiguate, but with a single encoder there is nothing to confuse it
            # with. Two-or-more encoders and no link is refused below rather than guessed at.
            only = next(iter(encoders.values())).get("inputs", {}).get("text")
            prompt = only if isinstance(only, str) else None
        if prompt is not None and not prompt.strip():
            prompt = None
        if prompt is None:
            neg = text_via("negative")
            return self._err(400, "could not identify the positive prompt in this workflow"
                             + (" (the KSampler's positive input resolved to an empty string; "
                                "refusing to render the negative prompt instead)"
                                if neg else ""))

        aspect, resolution = geometry(latent.get("width"), latent.get("height"))
        seed = sampler.get("seed")
        if isinstance(seed, int):
            seed = seed % 100000        # ComfyUI seeds are 32-bit; Flow's observed seeds are small
        else:
            seed = None

        # Deadlines sized to OmniRoute's 300s window, not the direct face's 600s+900s. Waiting 900s
        # for a free account, then rendering for 600s, guarantees OmniRoute has already given up --
        # so the credits would be spent on a video it can never fetch.
        job, err = start_job(prompt=prompt, model_name=ckpt, aspect=aspect, resolution=resolution,
                             seed=seed, requested_account=None, face="comfyui",
                             budget=COMFY_BUDGET, acquire_timeout=COMFY_ACQUIRE_TIMEOUT)
        if err:
            return self._err(400, err)
        log(f"{job['id'][:8]} comfyui face: ckpt={ckpt!r} -> {job['model']} {resolution} {aspect} "
            f"(budget {COMFY_BUDGET}s inside OmniRoute's {OMNIROUTE_COMFY_WINDOW}s window)")
        return self._json(200, {"prompt_id": job["id"], "number": STORE.stats()["total"],
                                "node_errors": {}})


# --------------------------------------------------------------------------- commands


LOOPBACK = ("127.0.0.1", "localhost", "::1", "")


class Server(ThreadingHTTPServer):
    # HTTPServer sets allow_reuse_address = 1. On Windows SO_REUSEADDR lets a second process bind an
    # address another process already holds, so the "is this port free" check below would pass while
    # a stranger keeps serving on it. For a process that spends money, a contested port has to be a
    # hard failure rather than a silent second listener.
    allow_reuse_address = False
    daemon_threads = True


def serve(a) -> int:
    global FLEET, DRY_RUN
    FLEET = load_accounts()
    DRY_RUN = bool(a.dry_run)

    if a.bind not in LOOPBACK and not a.token:
        raise SystemExit("refusing to bind %s without --token: this process spends real credits"
                         % a.bind)
    Base.token = a.token

    # The ComfyUI face cannot be authenticated: OmniRoute's comfyui provider is authType "none", so
    # it has no way to send a token, and --token therefore protects the direct face only. Since POST
    # /prompt on that face spends real credits, it is pinned to loopback whatever --bind says.
    # OmniRoute runs on this machine, so nothing is lost by refusing to publish it.
    comfy_bind = "127.0.0.1"
    if a.bind not in LOOPBACK:
        log(f"note: direct face on {a.bind} (token required); ComfyUI face pinned to 127.0.0.1 "
            f"because it cannot be authenticated and POST /prompt spends credits")

    if DRY_RUN:
        log("DRY RUN: no Flow call will be made and no credits spent; cached bytes are served")
        log(f"  stand-in media: {_dry_media() or 'NONE CACHED -- jobs will fail'}")
    else:
        log("probing accounts...")
        FLEET.probe_all()
        for acct in FLEET.accounts:
            mark = "ok " if acct.ready else "DOWN"
            log(f"  [{mark}] {acct.label:<10} port {acct.port}  {acct.email or '-'}  "
                f"credits={acct.credits}  {'' if acct.ready else acct.reason}")
        if not any(x.ready for x in FLEET.accounts):
            log("no account is ready -- serving anyway; run `python flow_shim.py doctor` to see why")
        threading.Thread(target=FLEET.refresh_loop, daemon=True).start()

    servers = []
    for handler, bind, port, name in ((DirectHandler, a.bind, a.direct_port, "direct"),
                                      (ComfyHandler, comfy_bind, a.comfy_port, "comfyui")):
        if port <= 0:
            continue
        try:
            s = Server((bind, port), handler)
        except OSError as e:
            for done, _, _ in servers:
                done.shutdown()
            raise SystemExit(f"cannot bind {name} face on {bind}:{port}: {e}")
        servers.append((s, name, port))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        log(f"{name:<8} face on http://{bind}:{port}")

    log("")
    log(f"filmmaking app  ->  POST http://{a.bind}:{a.direct_port}/v1/videos/generations")
    log(f"OmniRoute       ->  model \"comfyui/veo-3.1-fast\" (comfyui baseUrl defaults to :8188)")
    log("ctrl-c to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log("stopping")
        FLEET._stop.set()
        for s, _, _ in servers:
            s.shutdown()
    return 0


def cmd_accounts(a) -> int:
    global FLEET
    FLEET = load_accounts()
    FLEET.probe_all()
    print(f"{'label':<10} {'port':>5}  {'email':<32} {'credits':>8}  {'tier':<18} status")
    for x in FLEET.accounts:
        print(f"{x.label:<10} {x.port:>5}  {(x.email or '-'):<32} {str(x.credits):>8}  "
              f"{(x.tier or '-'):<18} {'ok' if x.ready else x.reason}")
    total = sum(x.credits or 0 for x in FLEET.accounts if x.ready)
    print()
    print(f"{total} credits across {sum(1 for x in FLEET.accounts if x.ready)} ready account(s)"
          f"  ~= {total // EST_COST} clips at the measured {EST_COST}/clip")
    return 0


def cmd_add(a) -> int:
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
           if ACCOUNTS_FILE.exists() else {"accounts": []})
    if any(x["port"] == a.port for x in raw.get("accounts", [])):
        print(f"port {a.port} is already registered")
        return 1
    raw.setdefault("accounts", []).append(
        {"label": a.label or f"acct-{a.port}", "port": a.port, "enabled": True})
    ACCOUNTS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"added {a.label or ''} port {a.port} to {ACCOUNTS_FILE}")
    return 0


CHAIN_HELP = {
    "chrome": "Start that account's Chrome with its OWN profile directory and "
              "--remote-debugging-port=<port>. Never the operator's live profile.",
    "tab": "In that Chrome, open labs.google/fx/tools/flow and enter a PROJECT, so the URL "
           "contains /project/<uuid>. The shim reads the project id from the URL.",
    "session": "The tab is signed out or its session went stale. Reload the tab; if it asks for "
               "a login, sign in by hand once -- automation never types a password here.",
    "sitekey": "The page did not expose a reCAPTCHA sitekey. Reload the tab and let it settle.",
    "credits": "The credits RPC refused this bearer. Usually a signed-out tab; reload and re-check.",
    "captcha": "grecaptcha.enterprise.execute failed in the page. Reload the tab.",
    "accepted": "A minted token was REJECTED by the submit RPC. Google most likely renamed the "
                "action label. Re-capture it with googleflow_click_capture.py (arm, click Create "
                "once, verify) and update RECAPTCHA_ACTION in googleflow_client.py.",
}


def cmd_doctor(a) -> int:
    """Walk the whole chain per account and name the first broken link.

    This is the answer to 'what do I do when it stops working': every dependency that can rot is
    tested in the order it is used, and each failure prints the specific repair.
    """
    global FLEET
    FLEET = load_accounts()
    bad = 0
    for acct in FLEET.accounts:
        print("=" * 78)
        print(f"{acct.label}  (port {acct.port})")
        print("=" * 78)

        def step(name, ok, detail=""):
            print(f"  [{'ok ' if ok else 'FAIL'}] {name:<26} {detail}")
            return ok

        try:
            assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who="flow_shim doctor")
        except Exception as e:
            if is_refusal(e):
                step("live-profile guard", False, "REFUSED -- this port is the operator's Chrome")
                print(f"\n  FIX: {CHAIN_HELP['chrome']}\n")
                bad += 1
                continue
            raise
        step("live-profile guard", True, "not the operator's profile")

        try:
            targets = [t for t in list_targets(acct.port) if t.get("type") == "page"]
        except Exception as e:
            step("chrome debug port", False, f"{type(e).__name__}: {str(e)[:60]}")
            print(f"\n  FIX: {CHAIN_HELP['chrome']}\n")
            bad += 1
            continue
        step("chrome debug port", True, f"{len(targets)} page target(s)")

        flow = [t for t in targets if FLOW_MATCH in (t.get("url", "") + t.get("title", "")).lower()]
        if not step("flow tab open", bool(flow), flow[0].get("url", "")[:60] if flow else "none"):
            print(f"\n  FIX: {CHAIN_HELP['tab']}\n")
            bad += 1
            continue

        try:
            sess = gf.FlowSession(FLOW_MATCH, port=acct.port).refresh()
        except Exception as e:
            step("session token", False, gf.scrub(str(e))[:70])
            print(f"\n  FIX: {CHAIN_HELP['session']}\n")
            bad += 1
            continue
        step("session token", True, f"{sess.email} expires {sess.expires}")

        if not step("project id", bool(sess.project_id), sess.project_id or "not in a project"):
            print(f"\n  FIX: {CHAIN_HELP['tab']}\n")
            bad += 1
            continue
        if not step("recaptcha sitekey", bool(sess.sitekey), (sess.sitekey or "")[:24]):
            print(f"\n  FIX: {CHAIN_HELP['sitekey']}\n")
            bad += 1
            continue

        c = gf.credits_now(sess)
        if not step("credits rpc", c is not None, f"{c} credits, tier {sess.tier}"):
            print(f"\n  FIX: {CHAIN_HELP['credits']}\n")
            bad += 1
            continue

        try:
            captcha = sess.mint_captcha()
        except Exception as e:
            step("captcha mint", False, gf.scrub(str(e))[:70])
            print(f"\n  FIX: {CHAIN_HELP['captcha']}\n")
            bad += 1
            continue
        step("captcha mint", True, f"{len(captcha)} chars")

        if a.deep:
            # Zero credits: an EMPTY prompt cannot generate anything, so a complaint about the
            # ARGUMENT is proof the captcha gate was passed.
            body = gf.build_submit_body("", captcha, sess.project_id, tier=sess.tier)
            st, text = gf.request(gf.SUBMIT_URL, sess.token, body)
            kind = gf.classify(text)
            if not step("captcha accepted", kind == "ARGUMENT", f"HTTP {st} {kind} (0 credits)"):
                print(f"      {gf.scrub(text)[:180]}")
                print(f"\n  FIX: {CHAIN_HELP['accepted']}\n")
                bad += 1
                continue
        print()
    print("=" * 78)
    if bad:
        print(f"  {bad} account(s) need attention -- see the FIX line under each.")
    else:
        n = len(FLEET.accounts)
        print(f"  All {n} account(s) healthy end to end"
              + ("" if a.deep else "; add --deep to also prove the captcha is still accepted"))
    print("=" * 78)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run both faces")
    s.add_argument("--bind", default="127.0.0.1")
    s.add_argument("--direct-port", type=int, default=DIRECT_PORT)
    s.add_argument("--comfy-port", type=int, default=COMFY_PORT,
                   help="0 to disable the ComfyUI face")
    s.add_argument("--token", default=os.environ.get("FLOW_SHIM_TOKEN") or None,
                   help="require this bearer on the direct face")
    s.add_argument("--dry-run", action="store_true",
                   help="serve cached bytes instead of calling Flow; spends nothing")
    s.set_defaults(fn=serve)

    c = sub.add_parser("accounts", help="registry plus live balances")
    c.set_defaults(fn=cmd_accounts)

    d = sub.add_parser("add", help="register another account's Chrome port")
    d.add_argument("port", type=int)
    d.add_argument("--label", default="")
    d.set_defaults(fn=cmd_add)

    o = sub.add_parser("doctor", help="find and explain the broken link")
    o.add_argument("--deep", action="store_true",
                   help="also send a zero-credit empty-prompt submit to prove the captcha works")
    o.set_defaults(fn=cmd_doctor)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {gf.scrub(str(exc))[:500]}")
        if os.environ.get("FLOW_SHIM_TRACE"):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
