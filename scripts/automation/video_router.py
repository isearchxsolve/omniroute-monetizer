"""video_router.py -- serve Google Flow AND rtst.ai as one local video API, with rotation.

WHY THIS EXISTS
---------------
Two providers are proven end to end and each arrived with its own code. Google Flow arrived with a
rotation engine welded to it (highest-balance-first account selection, a reservation floor, one lock
per account held across submit+poll, an append-only job log, two HTTP faces). rtst.ai arrived as a
one-shot CLI with none of that. Duplicating the engine per provider is not an option -- two
processes cannot both bind :8188, and a money bug fixed in one copy would live on in the other -- so
the engine stays singular HERE and everything provider-shaped lives behind video_provider.Provider.

    video_provider.py        the seam: Provider, Account, Step, REGISTRY, resolve_model, the floor
    video_provider_flow.py   Google Flow (Veo 3.1) -- wraps googleflow_client
    video_provider_rtst.py   rtst.ai (Vidu Q2 et al.) -- wraps rtst_client
    video_router.py          this file: registry, rotation, jobs, self-heal, two HTTP faces, CLI

TWO FACES OVER ONE JOB ENGINE

  :8189  the honest one -- POST /v1/videos/generations, GET the job, GET the MP4 bytes, plus a FREE
         POST /v1/videos/quote. Use this from the filmmaking app. Serves every provider.
  :8188  the ComfyUI costume -- POST /prompt, GET /history/{id}, GET /view?filename=...
         Use this to make `comfyui/veo-3.1-fast` work as an OmniRoute model string.

OmniRoute cannot be pointed at Flow directly: its compiled google-flow handler calls
/v1:generateVideo and /v1:fetchOperation, neither path exists on Flow's host, and both are baked
into a compiled chunk. But OmniRoute's `comfyui` video format is operator-steerable -- its base URL
comes from the credential's providerSpecificData.baseUrl (default http://localhost:8188) and it
authenticates with nothing (authType "none"). So a process speaking ComfyUI's three-call contract on
:8188 IS a working route through OmniRoute with zero OmniRoute code change.

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
    error channel, so a failure reaches OmniRoute as a timeout ~300s later. The direct face reports
    the same failure in seconds, which is why the filmmaking app should use the direct face.

WHICH MODELS LAND WHERE is a registry fact, not code: a ckpt_name is routed by whichever provider
claims it in its `aliases`. Both of OmniRoute's registered comfyui ids ("animatediff", "svd-xt")
are claimed by Flow today; re-pointing "svd-xt" at rtst is one line moved between two adapters.

WHY A BROWSER MUST STAY RUNNING: Flow's bearer is a web session token read from
labs.google/fx/api/auth/session and its reCAPTCHA token can only be minted by Google's own JS inside
a real page; rtst's bearer lives in that tab's localStorage. Neither has a server-side equivalent.
The Chrome windows can be minimised and unfocused and nobody has to click anything -- but they must
be alive. Two providers can share ONE Chrome on one port (different tabs, independent balances,
therefore independent locks), which is exactly how port 9222 is registered today.

SAFETY PROPERTIES THIS FILE IS RESPONSIBLE FOR
  * assert_cdp_safe() on every account port (inside each adapter's probe), so a profile
    misconfigured onto the operator's live Chrome is refused rather than risking the session
    revocation described in chrome_live_guard.py. A refusal disables the account permanently.
  * one lock per ACCOUNT held across submit+poll, so two jobs can never race the same balance.
  * confirm() runs on the reserved account before any spend, and may refuse for free.
  * NO automatic submit retry, ever: neither provider offers an idempotency key, so a retry after a
    submit that actually landed mints and charges a second video.
  * binds to 127.0.0.1 by default; a non-loopback bind REQUIRES --token, because this process
    spends real money. The ComfyUI face is pinned to loopback unconditionally.
  * bearers, captcha tokens and cookies stay in memory, are never logged and never persisted; every
    error string goes through scrub() before it is logged or returned.
  * self-heal relaunches Chrome and reopens tabs, but ONLY for a dead port or a missing tab -- never
    for a login wall, and never on a busy account. Opening a tab is navigation only; nothing is
    clicked, so healing cannot spend a credit.

    python video_router.py doctor      # which link in which chain is broken, and what to do
    python video_router.py accounts    # registry + live balances, per provider
    python video_router.py quote --model vidu --duration 3 --resolution 540    # free, exact
    python video_router.py wake --dry-run                                     # recovery plan
    python video_router.py serve       # run both faces
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import video_provider as vp  # noqa: E402
# Importing an adapter registers it. Nothing else in this file names a provider class, so adding a
# third provider is one import plus one adapter file.
import video_provider_flow  # noqa: E402,F401
import video_provider_rtst  # noqa: E402,F401
from cdp import DEFAULT_PORT, Page, list_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"

# New per-provider registry and job log. The Flow-only originals are READ (so no history or
# registration is lost) and never written, so an operator can still run the old shim off them.
ACCOUNTS_FILE = STATE / "video_accounts.json"
JOBS_FILE = STATE / "video_jobs.jsonl"
LEGACY_ACCOUNTS_FILE = STATE / "flow_accounts.json"
LEGACY_JOBS_FILE = STATE / "flow_jobs.jsonl"

# A dry run is a rehearsal: no credit moves and no media exists, so its record belongs nowhere near
# the ledger that answers "what did this machine spend and what did it get". MEASURED 2026-08-24:
# 40 dry-run records from the smoke suite had accumulated in video_jobs.jsonl, every one of them
# status=succeeded with credits_charged=0 and a borrowed file path -- indistinguishable at a glance
# from paid work, and load() was replaying them into the in-memory history an integrator would read.
DRYRUN_JOBS_FILE = STATE / "video_jobs.dryrun.jsonl"

DEFAULT_PROFILE = "providers"      # the safe_profile_dir() tag the proven Chrome actually uses

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
NON_FATAL = vp.NON_FATAL
log = vp.log
scrub = vp.scrub

# CHARSET, not length. The old floor was {6,80}, which 404s EVERY rtst clip: rtst ids are 5
# characters (measured: 96089). Length was never the guard -- the charset is, because it excludes
# "/", "\", "." and ":" so no id can name a path, and every resolved path is additionally
# containment-checked against the registered out dirs (see _contained).
MEDIA_ID_RE = re.compile(r"^[0-9A-Za-z_\-]{1,80}$")

# -- self-heal tuning -------------------------------------------------------------------------
# A self-healing launcher is the one thing here that can misbehave entirely on its own, so the rate
# limit is per PORT (flow and rtst share 9222) and it doubles on consecutive failures. Without this,
# a Chrome that refuses to start becomes a launch loop.
HEAL_BACKOFF_MIN = 300
HEAL_BACKOFF_MAX = 1800
HEAL_PORT_WAIT = 25          # seconds to wait for a relaunched Chrome's debug port
HEAL_TAB_WAIT = 30           # seconds to wait for a reopened tab to reach readyState complete
# A woken tab either evaluates at once or is not really awake: the measured recovery answered
# document.readyState in 0.4s, while a still-discarded one hangs until the deadline. Short on purpose
# -- the probe's own 60s timeout is what made a discarded tab expensive to discover in the first place.
WAKE_EVAL_TIMEOUT = 15

Account = vp.Account         # re-exported: the registry, the fleet and the smoke test all use it


def _contained(p: pathlib.Path) -> pathlib.Path | None:
    """The resolved path if it sits inside ANY registered provider's out dir, else None.

    This is the traversal guard, not decoration. It iterates vp.out_dirs() rather than hard-coding
    one provider's directory: Flow writes to state/harvest/flow and rtst to state/harvest/rtst, and a
    check against only the first silently 404s every clip from the second.
    """
    try:
        rp = pathlib.Path(p).resolve()
    except (OSError, ValueError):
        return None
    for d in vp.out_dirs():
        try:
            rp.relative_to(pathlib.Path(d).resolve())
            return rp
        except (ValueError, OSError):
            continue
    return None


def provider_of(acct: Account) -> vp.Provider | None:
    return vp.get(acct.provider)


# --------------------------------------------------------------------------- chrome launch recipe


def find_chrome() -> pathlib.Path:
    """Copied from drive.py:240 (find_chrome) rather than imported: drive.py is a 300-line CLI with
    its own argparse and module-level state, and pulling it in for 12 lines of path lookup would
    make the router depend on a tool it does not otherwise use."""
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        p = pathlib.Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if p.exists():
            return p
    raise RuntimeError("Chrome not found in Program Files or LocalAppData")


# --------------------------------------------------------------------------- the fleet


class Fleet:
    """Every registered account across every provider, their live balances, and the rule for
    choosing one. Provider-agnostic: it asks the adapter to probe and never inspects a browser
    itself, except when healing (which is about the browser, not about the provider)."""

    REFRESH_EVERY = 90

    def __init__(self, accounts: list[Account], raw: dict | None = None):
        self.accounts = accounts
        self.raw = raw if isinstance(raw, dict) else {"accounts": []}
        self._select = threading.Lock()
        self._save = threading.Lock()
        self._stop = threading.Event()
        self.self_heal = True
        # One heal in flight per PORT, because flow and rtst share 9222 and two simultaneous
        # relaunches of the same Chrome would race ProcessSingleton.
        self._port_locks: dict[int, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        self._heal_after: dict[int, float] = {}    # port -> earliest next launch attempt
        self._heal_fails: dict[int, int] = {}      # port -> consecutive launch failures
        self._wake_after: dict[str, float] = {}    # account key -> earliest next tab wake
        self._wake_fails: dict[str, int] = {}      # account key -> consecutive wake failures
        self.heal_stats = {"launched": 0, "tabs_opened": 0, "tabs_woken": 0, "failed": 0,
                           "not_healable": 0, "last": None}

    def _port_lock(self, port: int) -> threading.Lock:
        with self._locks_lock:
            return self._port_locks.setdefault(int(port), threading.Lock())

    # -- balances ---------------------------------------------------------------------------

    def probe(self, acct: Account) -> None:
        """Refresh one account through its adapter. Never raises: an account being down is a state
        to report and route around, not an error that takes the server with it. The adapter promises
        the same, but a provider bug must not be able to kill the refresh loop either."""
        prov = provider_of(acct)
        if prov is None:
            acct.ready, acct.fault = False, vp.FAULT_OTHER
            acct.reason = (f"no adapter registered for provider {acct.provider!r}; known: "
                           + ", ".join(sorted(vp.REGISTRY)))
            return
        try:
            prov.probe(acct)
        except NON_FATAL as e:
            acct.ready, acct.fault = False, vp.FAULT_OTHER
            acct.reason = f"{type(e).__name__}: {scrub(e)[:160]}"

    def probe_all(self, parallel: bool = True) -> None:
        """Probe every idle account. Accounts mid-generation are skipped, not waited for: probing can
        reload a tab (Flow's session self-heal does), and doing that underneath a job whose credits
        are already spent destroys the generation. A skipped account keeps its last known balance,
        which is correct anyway -- it is busy, so the rotation would not pick it.
        """
        targets = [a for a in self.accounts if a.enabled and a.lock.acquire(blocking=False)]
        try:
            if not parallel:
                for a in targets:
                    self.probe(a)
            else:
                ts = [threading.Thread(target=self.probe, args=(a,), daemon=True) for a in targets]
                [t.start() for t in ts]
                [t.join(timeout=120) for t in ts]
        finally:
            for a in targets:
                try:
                    a.lock.release()
                except RuntimeError:
                    pass
        self.save_urls()

    def save_urls(self) -> bool:
        """Persist any URL an adapter learned during probe, atomically, only when something changed.

        This one field is what makes recovery from a closed Chrome mechanical: Flow's project id
        exists ONLY in its tab URL, so reopening labs.google/fx generically restores a browser but
        not a working account. Everything else in the file is left exactly as the operator wrote it.
        """
        with self._save:
            entries = self.raw.get("accounts")
            if not isinstance(entries, list):
                return False
            changed = False
            for acct in self.accounts:
                if not acct.url:
                    continue
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    same = (str(e.get("provider") or "flow").lower() == acct.provider
                            and (e.get("label") or "") == acct.label
                            and int(e.get("port") or 0) == acct.port)
                    if same and e.get("url") != acct.url:
                        e["url"] = acct.url
                        changed = True
            if not changed:
                return False
            try:
                ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = ACCOUNTS_FILE.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(self.raw, indent=2), encoding="utf-8")
                os.replace(tmp, ACCOUNTS_FILE)     # atomic: a torn registry would be unloadable
                log(f"remembered tab URL(s) in {ACCOUNTS_FILE.name}")
                return True
            except OSError as e:
                log(f"could not write {ACCOUNTS_FILE.name}: {type(e).__name__}: {e}")
                return False

    def refresh_loop(self) -> None:
        """Never allowed to die. A dead refresh loop freezes every balance at its last value and the
        rotation then routes on stale numbers -- including routing to an account that no longer has
        the credits for the job. Self-heal runs here, after the probe that classified the faults."""
        while not self._stop.wait(self.REFRESH_EVERY):
            try:
                self.probe_all()
                if self.self_heal:
                    self.heal()
            except NON_FATAL as e:
                log(f"refresh loop: {type(e).__name__}: {scrub(str(e))[:120]} -- continuing")

    # -- self-heal --------------------------------------------------------------------------
    #
    # Credentials survive a closed Chrome (cookies and localStorage are on disk under
    # state/automation_profiles), but the TABS do not come back, and Flow's project id is parsed out
    # of its tab URL -- so relaunching the browser alone is not enough and nothing else in the repo
    # remembers the project URL. Hence: relaunch, then reopen the remembered URL, then re-probe.
    #
    # ONLY three faults are heal-able, and every one of them is fixed by launching or navigating:
    # a dead port (relaunch Chrome), a missing tab (open the URL), a discarded renderer (activate it,
    # then reload if that was not enough). FAULT_AUTH is deliberately excluded: relaunching cannot fix
    # a login wall, no password is ever typed here, and retrying would be a launch loop. Per
    # chrome_live_guard, a login wall in automation's own profile is a correct, reportable outcome.

    def _port_alive(self, port: int) -> bool:
        try:
            list_targets(int(port))
            return True
        except NON_FATAL:
            return False

    def _may_attempt(self, port: int) -> tuple[bool, float]:
        """Rate limit, per port: at most one launch per HEAL_BACKOFF_MIN, doubling to
        HEAL_BACKOFF_MAX after consecutive failures. Returns (allowed, seconds_to_wait)."""
        return self._gate_check(self._heal_after, int(port))

    def _arm_backoff(self, port: int, ok: bool) -> None:
        self._gate_arm(self._heal_after, self._heal_fails, int(port), ok)

    def _may_wake(self, acct: Account) -> tuple[bool, float]:
        """The same rate limit for waking a discarded tab, but on its own counter keyed by ACCOUNT
        rather than by port. Relaunching a dead Chrome and re-activating a discarded tab are different
        actions with different causes and different costs: a Chrome that refuses to start must not
        also freeze out the cheap HTTP activation of a sibling tab on the same port for half an hour.
        Successful wakes arm it too, so a tab Chrome keeps re-discarding cannot become a wake loop."""
        return self._gate_check(self._wake_after, acct.key)

    def _arm_wake(self, acct: Account, ok: bool) -> None:
        self._gate_arm(self._wake_after, self._wake_fails, acct.key, ok)

    @staticmethod
    def _gate_check(after: dict, key) -> tuple[bool, float]:
        left = after.get(key, 0.0) - time.time()
        return (left <= 0), max(0.0, left)

    @staticmethod
    def _gate_arm(after: dict, fails: dict, key, ok: bool) -> None:
        n = 0 if ok else fails.get(key, 0) + 1
        fails[key] = n
        after[key] = time.time() + min(HEAL_BACKOFF_MIN * (2 ** max(0, n - 1)), HEAL_BACKOFF_MAX)

    def _launch_chrome(self, acct: Account, dry_run: bool = False) -> tuple[bool, str]:
        """Relaunch this account's Chrome on its own profile dir at its own port.

        The flag set and the detached-launch technique are copied from drive.py:251-274
        (start_chrome) rather than imported, for the reason given on find_chrome above. Keep the two
        in step: --remote-allow-origins=* is what lets a websocket from this process attach at all.
        """
        udd = vp.safe_profile_dir(acct.profile)
        try:
            vp.assert_safe(udd, who="video_router heal")     # can never be the operator's live dir
        except Exception as e:
            return False, f"profile dir refused by the live guard: {scrub(e)[:120]}"
        if int(acct.port) in vp.live_devtools_ports():
            # Belt and braces on top of assert_cdp_safe: if the operator's own Chrome is advertising
            # this port right now, launching a second one against it is exactly the accident
            # chrome_live_guard exists to prevent.
            return False, f"port {acct.port} is currently served by a live Chrome -- refusing"
        try:
            chrome = find_chrome()
        except RuntimeError as e:
            return False, str(e)
        if dry_run:
            return True, f"would launch {chrome.name} --user-data-dir={udd} " \
                         f"--remote-debugging-port={acct.port}"

        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(
                [str(chrome),
                 f"--user-data-dir={udd}",
                 f"--remote-debugging-port={acct.port}",
                 "--remote-allow-origins=*",
                 "--no-first-run", "--no-default-browser-check", "--disable-sync",
                 "--window-size=1400,950", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                creationflags=flags, close_fds=True)
        except OSError as e:
            return False, f"launch failed: {type(e).__name__}: {e}"
        for _ in range(HEAL_PORT_WAIT):
            time.sleep(1)
            if self._port_alive(acct.port):
                return True, f"chrome up on port {acct.port} (profile {acct.profile})"
        return False, f"launched but port {acct.port} never came up in {HEAL_PORT_WAIT}s"

    def _open_tab(self, acct: Account, dry_run: bool = False) -> tuple[bool, str]:
        """Open the remembered URL in this account's Chrome. Navigation only -- nothing is clicked,
        no generate button is touched, so this cannot spend a credit."""
        prov = provider_of(acct)
        if prov is None:
            return False, f"no adapter for provider {acct.provider!r}"
        url = acct.url or prov.default_url
        if not url:
            return False, f"no URL remembered for {acct.label} and no default_url on {prov.name}"
        if dry_run:
            return True, f"would open {url}"
        try:
            vp.assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who="video_router heal")
        except Exception as e:
            return False, f"live guard refused port {acct.port}: {scrub(e)[:120]}"

        try:
            self._create_target(acct.port, url)
        except NON_FATAL as e:
            return False, f"could not open a tab: {type(e).__name__}: {scrub(e)[:120]}"

        # Wait for the tab to actually exist and finish loading, so the re-probe that follows reads a
        # settled page rather than an about:blank that has not navigated yet.
        for _ in range(HEAL_TAB_WAIT):
            time.sleep(1)
            try:
                hit = [t for t in list_targets(acct.port)
                       if t.get("type") == "page"
                       and prov.tab_match in (t.get("url", "") + t.get("title", "")).lower()]
            except NON_FATAL:
                continue
            if not hit:
                continue
            try:
                with Page(prov.tab_match, port=acct.port) as p:
                    if p.evaluate("document.readyState", timeout=15) == "complete":
                        return True, f"opened {(hit[0].get('url') or url)[:70]}"
            except NON_FATAL:
                continue
        return False, f"tab for {prov.name} did not settle within {HEAL_TAB_WAIT}s"

    def _wake_tab(self, acct: Account, dry_run: bool = False) -> tuple[bool, str]:
        """Bring a discarded tab's renderer back. Navigation only, so it cannot spend a credit.

        MEASURED 2026-08-24: after both automation tabs sat idle, Chrome's memory saver discarded
        their renderers. /json/list still listed them, a page websocket still attached in 0.0s, and
        browser-domain calls answered instantly -- but every Runtime.evaluate hung until the deadline,
        because a discarded tab has no execution context. GET /json/activate/<targetId> re-created it,
        after which document.readyState came back in 0.4s.

        Two steps, cheapest first: activate, and only if the tab still will not evaluate, one
        Page.navigate to the URL it is already on. Navigate is dispatched by the browser process
        rather than the renderer, so it works on a tab that cannot run JS -- it is the same one-reload
        recovery the Flow adapter already does for a stale session, and Flow's project id survives it
        because the URL is unchanged.
        """
        prov = provider_of(acct)
        if prov is None:
            return False, f"no adapter for provider {acct.provider!r}"
        try:
            vp.assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who="video_router wake-tab")
        except Exception as e:
            return False, f"live guard refused port {acct.port}: {scrub(e)[:120]}"
        try:
            tabs = [t for t in list_targets(acct.port)
                    if t.get("type") == "page"
                    and prov.tab_match in (t.get("url", "") + t.get("title", "")).lower()]
        except NON_FATAL as e:
            return False, f"port {acct.port} stopped answering: {type(e).__name__}"
        if not tabs:
            # The tab went away between the probe and now, which is the other heal-able fault and is
            # handled by a different branch. Say so instead of activating a target id that is gone.
            return False, f"no {prov.name} tab on port {acct.port} any more -- it is a missing tab now"
        target, url = tabs[0].get("id"), tabs[0].get("url") or acct.url or prov.default_url
        if dry_run:
            return True, (f"would activate target {target} ({(url or '')[:50]}) on port {acct.port}"
                          f"; if it still would not evaluate, would navigate it to its own URL")
        if not target:
            return False, "target has no id in /json/list"

        def evaluates() -> bool:
            try:
                with Page(prov.tab_match, port=acct.port) as p:
                    return bool(p.evaluate("document.readyState", timeout=WAKE_EVAL_TIMEOUT))
            except NON_FATAL:
                return False

        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{int(acct.port)}/json/activate/"
                f"{urllib.parse.quote(str(target), safe='')}", timeout=20).read()
        except NON_FATAL as e:
            return False, f"activate refused: {type(e).__name__}: {scrub(e)[:100]}"
        if evaluates():
            return True, f"activated {(url or '')[:60]} -- it evaluates again"

        if not url:
            return False, "activated but it still will not evaluate, and no URL to navigate to"
        try:
            with Page(prov.tab_match, port=acct.port) as p:
                p.send("Page.navigate", {"url": url}, timeout=60)
        except NON_FATAL as e:
            return False, (f"activated but it still will not evaluate, and navigate failed: "
                           f"{type(e).__name__}: {scrub(e)[:100]}")
        for _ in range(HEAL_TAB_WAIT):
            time.sleep(1)
            if evaluates():
                return True, f"activated, then reloaded {(url or '')[:60]} -- it evaluates again"
        return False, (f"activated and reloaded, still not executing JS after {HEAL_TAB_WAIT}s "
                       f"-- Chrome may be out of memory")

    @staticmethod
    def _create_target(port: int, url: str) -> None:
        """Target.createTarget on the BROWSER endpoint. cdp.Page only attaches to page targets, and
        there is no page to attach to when the whole point is that the tab is missing.

        PUT /json/new is Chrome's HTTP alias for the same command (PUT, not GET, since M111); it is
        tried first because it needs no websocket, with the CDP call as the fallback.
        """
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{int(port)}/json/new?{urllib.parse.quote(url, safe=':/?&=%.-_')}",
                method="PUT")
            urllib.request.urlopen(req, timeout=20).read()
            return
        except NON_FATAL as http_err:
            first = http_err

        import websocket                          # already a hard dependency, via cdp.py
        raw = urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/json/version", timeout=20).read()
        ws_url = json.loads(raw).get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError(f"/json/new refused ({first}) and /json/version exposed no browser "
                               f"websocket")
        ws = websocket.create_connection(ws_url, timeout=30)
        try:
            ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": url}}))
            deadline = time.time() + 30
            while time.time() < deadline:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    if "error" in msg:
                        raise RuntimeError(f"Target.createTarget: {msg['error'].get('message')}")
                    return
            raise TimeoutError("Target.createTarget did not answer within 30s")
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _heal_one(self, acct: Account, dry_run: bool = False) -> dict | None:
        """Heal exactly one account, or explain why it was left alone. Returns an action record."""
        def rec(action, ok, detail):
            return {"account": acct.label, "provider": acct.provider, "port": acct.port,
                    "action": action, "ok": bool(ok), "detail": detail}

        if not acct.enabled or acct.ready:
            return None
        if acct.fault not in vp.HEALABLE:
            self.heal_stats["not_healable"] += 1
            why = ("signed out -- sign in by hand once; automation never types a password"
                   if acct.fault == vp.FAULT_AUTH else f"fault {acct.fault!r} is not heal-able")
            return rec("skip", False, f"{why}: {acct.reason}")
        # Never heal a busy account: healing reloads or reopens a tab, and doing that underneath a
        # job whose credits are already spent destroys the generation. Same rule as probe_all.
        if not acct.lock.acquire(blocking=False):
            return rec("skip", False, "busy with a job")
        plock = self._port_lock(acct.port)
        if not plock.acquire(blocking=False):
            acct.lock.release()
            return rec("skip", False, f"another heal is already in flight on port {acct.port}")
        try:
            # Re-derive rather than trust the probe's label: a sibling account on this same port may
            # already have relaunched Chrome a moment ago, in which case this is only a missing tab.
            fault = acct.fault
            if fault == vp.FAULT_PORT and self._port_alive(acct.port):
                fault = vp.FAULT_TAB

            if fault == vp.FAULT_FROZEN:
                allowed, wait = self._may_wake(acct)
                if not allowed:
                    return rec("skip", False, f"backoff: {wait:.0f}s before waking "
                                              f"{acct.label}'s tab again")
                ok, detail = self._wake_tab(acct, dry_run)
                if dry_run:
                    return rec("activate", ok, detail)
                self._arm_wake(acct, ok)
                self.heal_stats["tabs_woken" if ok else "failed"] += 1
                if ok:
                    self.probe(acct)
                    detail = f"{detail}; now {'ready' if acct.ready else acct.reason}"
                return rec("activate", ok and acct.ready, detail)

            if fault == vp.FAULT_PORT:
                allowed, wait = self._may_attempt(acct.port)
                if not allowed:
                    return rec("skip", False, f"backoff: {wait:.0f}s before the next launch on "
                                              f"port {acct.port}")
                ok, detail = self._launch_chrome(acct, dry_run)
                if not dry_run:
                    self._arm_backoff(acct.port, ok)
                    self.heal_stats["launched" if ok else "failed"] += 1
                if not ok:
                    return rec("launch", False, detail)
                if dry_run:
                    ok2, d2 = self._open_tab(acct, dry_run=True)
                    return rec("launch+tab", ok2, f"{detail}; then {d2}")
                ok, detail2 = self._open_tab(acct)
                if ok:
                    self.heal_stats["tabs_opened"] += 1
                else:
                    self.heal_stats["failed"] += 1
                self.probe(acct)
                return rec("launch+tab", ok and acct.ready, f"{detail}; {detail2}; "
                                                            f"now {'ready' if acct.ready else acct.reason}")

            ok, detail = self._open_tab(acct, dry_run)
            if dry_run:
                return rec("tab", ok, detail)
            self.heal_stats["tabs_opened" if ok else "failed"] += 1
            if ok:
                self.probe(acct)
                detail = f"{detail}; now {'ready' if acct.ready else acct.reason}"
            return rec("tab", ok and acct.ready, detail)
        finally:
            plock.release()
            try:
                acct.lock.release()
            except RuntimeError:
                pass

    def heal(self, dry_run: bool = False) -> list[dict]:
        """Try to bring every down-but-heal-able account back. Every action is logged; the counters
        land in /healthz. This is both the refresh loop's recovery step and the body of `wake`."""
        out = []
        for acct in self.accounts:
            r = self._heal_one(acct, dry_run=dry_run)
            if not r:
                continue
            out.append(r)
            mark = "ok  " if r["ok"] else ("plan" if dry_run else "----")
            log(f"heal [{mark}] {r['provider']}/{r['account']} port {r['port']}: "
                f"{r['action']}: {r['detail']}")
        if out and not dry_run:
            self.heal_stats["last"] = time.strftime("%H:%M:%S")
            self.save_urls()
        return out

    # -- the rotation rule ------------------------------------------------------------------

    def acquire(self, provider: str, need: int, requested: str | None = None,
                timeout: float = 900) -> Account:
        """Reserve an account of THIS provider, holding its lock. Caller MUST release it.

        Filtering by provider first is what keeps the two balances apart: handing a Flow account to
        an rtst job would submit a Vidu prompt against a Google session. Every refusal below names
        the provider, so "no account is ready" can never be read as being about the wrong pool.

        Highest balance first, so the fleet drains evenly rather than burning one account to zero
        while three sit full. The lock is held across submit AND poll: that is what makes the
        credits-before/after delta trustworthy and makes double-spend structurally impossible.
        """
        provider = str(provider).strip().lower()
        deadline = time.time() + timeout
        first_pass = True
        while time.time() < deadline:
            with self._select:
                pool = [a for a in self.accounts if a.enabled and a.provider == provider]
                if not pool:
                    raise RuntimeError(
                        f"no {provider} account is registered (registry has: "
                        + (", ".join(sorted({f'{a.provider}/{a.label}' for a in self.accounts}))
                           or "nothing")
                        + f"). Add one with: python {pathlib.Path(__file__).name} add "
                          f"--provider {provider} --port {DEFAULT_PORT}")
                if requested:
                    r = str(requested).strip().lower()
                    if r not in ("", "auto", "any"):
                        pool = [a for a in pool
                                if r in (str(a.port), a.label.lower(), (a.email or "").lower())]
                        if not pool:
                            raise RuntimeError(f"no {provider} account matches {requested!r}")
                if first_pass and not any(a.ready for a in pool):
                    self.probe_all()
                    first_pass = False
                ranked = sorted((a for a in pool if a.ready and (a.credits or 0) >= need),
                                key=lambda a: -(a.credits or 0))
                for acct in ranked:
                    if acct.lock.acquire(blocking=False):
                        return acct
                if not any(a.ready for a in pool):
                    raise RuntimeError(f"no {provider} account is ready: "
                                       + "; ".join(f"{a.label}: {a.reason}" for a in pool))
                if not any((a.credits or 0) >= need for a in pool if a.ready):
                    raise RuntimeError(
                        f"no {provider} account has the ~{need} credits this needs: "
                        + "; ".join(f"{a.label}={a.credits}" for a in pool if a.ready))
            time.sleep(2)
        raise RuntimeError(f"every {provider} account stayed busy for {timeout:.0f}s")


# --------------------------------------------------------------------------- the registry file


REGISTRY_NOTE = ("One entry per (provider, port, label). Two providers MAY share a port -- they are "
                 "different tabs in one Chrome with independent balances, so they get independent "
                 "locks. Each Chrome needs its OWN profile dir and --remote-debugging-port; never "
                 "point one at the operator's live Chrome profile. `url` is rewritten by the router "
                 "whenever a probe succeeds, and is what makes recovery from a closed Chrome "
                 "mechanical -- Flow's project id exists nowhere else.")


def _entry(a: dict) -> dict:
    """One registry entry, normalised. A missing provider means flow: that is what every entry in
    the Flow-only registry implicitly was."""
    return {"label": str(a.get("label") or ""),
            "provider": str(a.get("provider") or "flow").strip().lower(),
            "port": int(a.get("port") or DEFAULT_PORT),
            "profile": str(a.get("profile") or DEFAULT_PROFILE),
            "enabled": bool(a.get("enabled", True)),
            "url": a.get("url") or None}


def _migrate() -> dict | None:
    """Build the new registry from the Flow-only one. The original is READ ONLY -- it is left exactly
    as it is so the old shim keeps working off it, and so a failed migration costs nothing."""
    if not LEGACY_ACCOUNTS_FILE.exists():
        return None
    try:
        old = json.loads(LEGACY_ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"{LEGACY_ACCOUNTS_FILE.name} is unreadable ({type(e).__name__}) -- not migrating")
        return None
    entries = [_entry(a) for a in old.get("accounts", []) if isinstance(a, dict)]
    if not entries:
        return None
    return {"_note": REGISTRY_NOTE, "accounts": entries}


def load_accounts() -> Fleet:
    """The registry, migrating from the Flow-only file the first time and never touching it after."""
    if not ACCOUNTS_FILE.exists():
        STATE.mkdir(parents=True, exist_ok=True)
        raw = _migrate()
        if raw:
            ACCOUNTS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            log(f"migrated {len(raw['accounts'])} account(s) from {LEGACY_ACCOUNTS_FILE.name} to "
                f"{ACCOUNTS_FILE.name} as provider=flow; the original was not modified")
        else:
            raw = {"_note": REGISTRY_NOTE,
                   "accounts": [_entry({"label": "flow-pro-1", "provider": "flow",
                                        "port": DEFAULT_PORT})]}
            ACCOUNTS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            log(f"wrote a starter registry at {ACCOUNTS_FILE}")
        # Never register an account silently: a second provider means a second balance and a second
        # way to spend money, so the operator names it explicitly. But do say the exact command --
        # the proven Chrome on 9222 really does carry an rtst.ai tab alongside the Flow one.
        if not any(a["provider"] == "rtst" for a in raw["accounts"]):
            log(f"hint: port {DEFAULT_PORT} also carries an rtst.ai tab. To rotate it too, run: "
                f"python {pathlib.Path(__file__).name} add --provider rtst --port {DEFAULT_PORT} "
                f"--label rtst-1")

    try:
        raw = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"cannot read {ACCOUNTS_FILE}: {type(e).__name__}: {e}")
    if not isinstance(raw, dict) or not isinstance(raw.get("accounts"), list):
        raise SystemExit(f"{ACCOUNTS_FILE} must be an object with an \"accounts\" list")

    # Normalise in place so save_urls() writes back a file of the same shape it read.
    raw["accounts"] = [_entry(a) for a in raw["accounts"] if isinstance(a, dict)]
    accts, seen = [], set()
    for e in raw["accounts"]:
        if not e["label"]:
            e["label"] = f"{e['provider']}-{e['port']}"
        k = (e["provider"], e["port"], e["label"])
        if k in seen:
            log(f"duplicate registry entry {k} -- keeping the first")
            continue
        seen.add(k)
        if vp.get(e["provider"]) is None:
            log(f"{e['label']}: no adapter for provider {e['provider']!r} -- entry kept but it can "
                f"never be routed to (known: {', '.join(sorted(vp.REGISTRY))})")
        accts.append(Account(e["provider"], e["port"], e["label"], e["enabled"],
                             profile=e["profile"], url=e["url"]))
    if not accts:
        raise SystemExit(f"no accounts in {ACCOUNTS_FILE}")
    return Fleet(accts, raw)


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
        """Replay the append-only logs so a restart does not orphan finished videos.

        BOTH logs are read -- the Flow-only original and the new one -- so no history is lost, but
        only the new one is ever appended to. Anything the log still calls queued/active was in
        flight when the process died. Its thread is gone, so it can never progress: left as-is, a
        caller polls that job id forever. It is marked `interrupted` instead, and kept rather than
        dropped -- the provider may well have charged for it, so the record is the only trace of
        where the credits went.
        """
        for path in (LEGACY_JOBS_FILE, JOBS_FILE):        # oldest first: newer records win
            if not path.exists():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        j = json.loads(line)
                        if isinstance(j, dict) and j.get("id"):
                            j.setdefault("provider", "flow")   # pre-router records are all Flow
                            self.jobs[j["id"]] = j
            except Exception as e:
                log(f"{path.name} unreadable ({type(e).__name__}) -- skipping it")
        stale = [j for j in self.jobs.values() if j.get("status") in ("queued", "active")]
        for j in stale:
            prov = vp.get(j.get("provider") or "")
            where = str(prov.out_dir) if prov else "state/harvest/"
            j["status"] = "interrupted"
            j["error"] = ("the router restarted while this job was in flight; credits may already "
                          f"have been charged -- check the balance and {where} before retrying")
            j["finished"] = time.time()
        if stale:
            log(f"{len(stale)} job(s) were in flight at the last shutdown -> marked interrupted")
            for j in stale:
                log(f"  {j['id'][:8]} {j.get('provider')}/{j.get('model')} "
                    f"media={j.get('media_id')} charged={j.get('credits_charged')}")

    def create(self, **fields) -> dict:
        # Every key is created up front: _snap iterates this dict from HTTP threads while the worker
        # writes to it, and a dict that grows mid-iteration raises and kills the response.
        job = {"id": uuid.uuid4().hex, "status": "queued", "created": time.time(),
               "finished": None, "provider": None, "project_id": None, "dry_run": False,
               "account": None, "port": None, "media_id": None, "media_ids": [], "error": None,
               "credits_before": None, "credits_after": None, "credits_charged": None,
               "quoted": None, "media_count": None, "workflow_count": None, "flow_status": None,
               "duration": None, "durations": [], "bytes": None, "bytes_each": [],
               "bytes_total": None, "file": None, "files": [], **fields}
        with self.lock:
            self.jobs[job["id"]] = job
        self.persist(job)
        return job

    def persist(self, job: dict) -> None:
        # DRY_RUN is the process-wide flag and job["dry_run"] is set once run_job starts, so the
        # queued record written by create() -- which lands before that -- is caught by the global.
        path = DRYRUN_JOBS_FILE if (DRY_RUN or job.get("dry_run")) else JOBS_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
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
# poller, the base64 envelope, the filmmaking app's client -- without touching either provider, so
# the plumbing can be regression-tested for free instead of at 20 credits a go. It is surfaced in
# /healthz and on every job so a dry run can never be mistaken for a real one.
DRY_RUN = False


def _dry_media() -> pathlib.Path | None:
    """The newest already-downloaded clip from ANY provider, reused as stand-in bytes for a dry run.

    Scans every registered out dir rather than Flow's alone -- with only rtst clips on disk, a
    Flow-only scan makes every dry run fail with "no cached mp4".
    """
    best = None
    for d in vp.out_dirs():
        try:
            for f in pathlib.Path(d).glob("*.mp4"):
                if best is None or f.stat().st_mtime > best.stat().st_mtime:
                    best = f
        except OSError:
            continue
    return best


def run_job(job: dict) -> None:
    """Confirm, submit, poll, download. Owns one account for its whole life."""
    if DRY_RUN:
        job["dry_run"] = True
        job["status"] = "active"
        job["account"] = "(dry run -- no account used)"
        time.sleep(4)
        f = _dry_media()
        if not f:
            job["status"] = "failed"
            job["error"] = ("dry run has no cached mp4 to serve; run one real generation first "
                            "or drop --dry-run")
        else:
            size = f.stat().st_size
            job.update(status="succeeded", media_id=f.stem, media_ids=[f.stem], file=str(f),
                       files=[str(f)], bytes=size, bytes_each=[size], bytes_total=size,
                       credits_charged=0, duration="8s", durations=["8s"],
                       flow_status="SUCCESSFUL (simulated)", media_count=1, workflow_count=1)
        job["finished"] = time.time()
        log(f"{job['id'][:8]} DRY RUN {job['status']} -> {job.get('media_id')}")
        STORE.persist(job)
        return

    prov = vp.get(job["provider"])
    params = job["_params"]
    acct = None
    try:
        if prov is None:                     # start_job resolves the provider, so this is paranoia
            raise RuntimeError(f"no adapter for provider {job['provider']!r}")
        # estimate() is account-independent and only decides WHICH account is big enough. It is
        # deliberately allowed to be low: confirm() below runs on the reserved account and can still
        # refuse for free, whereas over-reserving strands accounts that could in fact have paid.
        need = prov.estimate(params)
        acct = FLEET.acquire(prov.name, need, job.get("requested_account"),
                             timeout=float(job.get("acquire_timeout") or 900))
        job["account"], job["port"] = acct.email or acct.label, acct.port
        job["status"] = "active"

        # THE pre-commit gate, on the account that was actually reserved. rtst re-quotes exactly here
        # and refuses on can_afford:false or quote > max_spend; Flow cannot be quoted, so it reports
        # its floor and its server-side balance check stays the only real gate. Either way, an error
        # here aborts with nothing spent.
        cost, err = prov.confirm(acct, params, max_spend=job.get("max_spend"))
        if err:
            raise RuntimeError(f"refused before spending anything: {err}")
        job["quoted"] = cost
        log(f"{job['id'][:8]} -> {prov.name}/{acct.label} ({job['model']}, "
            f"{job.get('resolution')} {job.get('aspect')}) "
            f"{'quoted' if prov.quotes_before_spending else 'estimated'} {cost} credits")

        r = prov.submit(acct, params)          # SPENDS. Never retried: no idempotency key exists.
        ids = [str(i) for i in (r.get("items") or []) if str(i or "").strip()]
        job["media_ids"] = ids
        job["media_id"] = ids[0] if ids else None
        job["media_count"] = r.get("media_count")
        job["workflow_count"] = r.get("workflow_count")
        job["project_id"] = r.get("project_id")
        job["credits_before"] = r.get("credits_before")
        job["credits_after"] = r.get("credits_after")
        if isinstance(job["credits_before"], int) and isinstance(job["credits_after"], int):
            job["credits_charged"] = job["credits_before"] - job["credits_after"]
            # Keyed by provider AND model, so rtst's 2-credit vidu floor cannot poison Flow's 20.
            vp.observe_cost(f"{prov.name}/{job['model']}", job["credits_charged"],
                            job["media_count"], fallback=prov.est_cost)
        if isinstance(job["credits_after"], int):
            acct.credits = job["credits_after"]
        if not ids:
            raise RuntimeError("submit returned no media id")
        # A quote that disagrees with the charge is the single most useful standing check on the money
        # path -- it is exactly how the 6-quoted/6-charged proof was made. Logged, never acted on.
        if (isinstance(job["quoted"], int) and isinstance(job["credits_charged"], int)
                and prov.quotes_before_spending and job["quoted"] != job["credits_charged"]):
            log(f"{job['id'][:8]} !! {prov.name} quoted {job['quoted']} but the balance moved "
                f"{job['credits_charged']} -- the quote and the charge disagree, check before "
                f"trusting either")
        log(f"{job['id'][:8]} submitted {len(ids)} item(s) ({', '.join(i[:12] for i in ids)})  "
            f"workflows={job['workflow_count']} charged={job['credits_charged']}")
        STORE.persist(job)

        # One shared deadline across all items, not `budget` each: a provider that returns several
        # medias renders them concurrently, and a per-item budget would let a 3-media job run 3x
        # longer than the caller asked for -- which for the comfy face means blowing straight through
        # OmniRoute's 300s window.
        deadline = time.time() + float(job.get("budget") or 600)
        files: list[str] = []
        sizes: list[int] = []
        durations: list = []
        for n, item in enumerate(ids, 1):
            def on_status(st, _n=n, _item=item):
                job["flow_status"] = f"[{_n}/{len(ids)}] {st}"
                log(f"{job['id'][:8]} [{_n}/{len(ids)}] {st}")

            left = deadline - time.time()
            if left < 10:
                raise RuntimeError(
                    f"budget exhausted after {n - 1}/{len(ids)} item(s); {len(ids) - n + 1} paid "
                    f"clip(s) not collected -- ids are recorded, fetch them with: "
                    + "; ".join(prov.recovery_hint(i) for i in ids[n - 1:]))
            meta = prov.wait(acct, item, budget=int(left), on_status=on_status)
            durations = durations + [prov.duration_of(meta)]
            dest = prov.download(acct, item, meta)
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
        job["error"] = f"{type(e).__name__}: {scrub(str(e))[:400]}"
        job["finished"] = time.time()
        log(f"{job['id'][:8]} FAILED {job['error']}")
        if job.get("media_ids") and not job.get("files"):
            hint = "; ".join(prov.recovery_hint(i) for i in job["media_ids"]) if prov else ""
            log(f"{job['id'][:8]} WARNING: credits were already charged for "
                f"{len(job['media_ids'])} item(s); nothing was downloaded. {hint}")
        if job.get("face") == "comfyui":
            log(f"{job['id'][:8]} note: the ComfyUI face has no error channel, so OmniRoute will "
                f"report this as a timeout ~{OMNIROUTE_COMFY_WINDOW}s from its submit")
    finally:
        if acct is not None:
            # If the submit response never reported a balance, this account's cached figure is
            # known-stale: routing on it can hand the account out for a job it can no longer pay for.
            # Marking it not-ready sends the next acquire() through probe_all instead of trusting
            # arithmetic we could not confirm. (Both adapters do report one -- Flow reads
            # remainingCredits, rtst re-reads /user/credits -- so this firing means something
            # upstream changed shape, which is exactly when the guard is needed.)
            if not DRY_RUN and job.get("credits_after") is None and job.get("media_ids"):
                acct.ready = False
                acct.reason = "balance unconfirmed after a charged submit; awaiting re-probe"
                log(f"{job['id'][:8]} {acct.label}: submit reported no balance after charging; "
                    f"marked for re-probe so routing cannot use a stale balance")
            try:
                acct.lock.release()
            except RuntimeError:
                pass
        STORE.persist(job)


def start_job(*, prompt: str, model_name: str | None, req: dict, requested_account: str | None,
              face: str, budget: int = 600, acquire_timeout: float = 900,
              max_spend: int | None = None) -> tuple[dict | None, str | None]:
    """Validate everything that can be validated for free, then spawn the worker.

    Order matters: the model is resolved, the provider validates its own params, and a provider with
    no registered account fails HERE -- before a thread exists and before an account is reserved.
    """
    if not prompt or not str(prompt).strip():
        return None, "prompt is required and cannot be empty"
    prov, key, err = vp.resolve_model(model_name)
    if err or prov is None or key is None:
        return None, err or f"unknown model {model_name!r}"
    if not any(a.enabled and a.provider == prov.name for a in FLEET.accounts):
        return None, (f"model {key!r} routes to {prov.name}, which has no enabled account "
                      f"registered; add one with: python {pathlib.Path(__file__).name} add "
                      f"--provider {prov.name} --port {DEFAULT_PORT}")
    params, err = prov.normalise({**req, "model": key, "prompt": str(prompt)})
    if err or params is None:
        return None, err or "provider rejected these parameters"
    params.setdefault("prompt", str(prompt))
    job = STORE.create(prompt=str(prompt), provider=prov.name, model=key,
                       aspect=params.get("aspect"), resolution=params.get("resolution"),
                       duration=params.get("duration"), seed=params.get("seed"),
                       requested_account=requested_account, face=face, budget=budget,
                       acquire_timeout=acquire_timeout,
                       max_spend=prov.max_spend_default if max_spend is None else max_spend,
                       model_key_proven=key in prov.proven, _params=params)
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job, None


def quote_once(model_name: str | None, req: dict, requested_account: str | None = None,
               timeout: float = 30) -> dict:
    """What would this cost? Free, read-only, no job created.

    Provided because rtst can answer exactly (GET /video/estimate-credits) and that is the whole
    difference between the two providers' money paths: a caller can know the price before spending.
    Flow answers with its floor and says so via `exact: false`.
    """
    prov, key, err = vp.resolve_model(model_name)
    if err or prov is None or key is None:
        return {"error": err or f"unknown model {model_name!r}"}
    params, err = prov.normalise({**req, "model": key,
                                  "prompt": str(req.get("prompt") or QUOTE_PROMPT)})
    if err or params is None:
        return {"provider": prov.name, "model": key, "error": err}
    out = {"provider": prov.name, "model": key, "params": params,
           "estimate": prov.estimate(params), "exact": bool(prov.quotes_before_spending),
           "max_spend_default": prov.max_spend_default, "quote": None, "error": None}
    try:
        # A short lock on a ready account: the quote is a read through that account's own tab, and
        # the balance it reports belongs to that account and no other.
        acct = FLEET.acquire(prov.name, 0, requested_account, timeout=timeout)
    except NON_FATAL as e:
        out["error"] = scrub(str(e))[:300]
        return out
    try:
        out["account"] = acct.label
        q, qerr = prov.quote(acct, params)
        out["quote"], out["error"] = q, (scrub(qerr)[:300] if qerr else None)
        out["balance"] = acct.credits
    finally:
        try:
            acct.lock.release()
        except RuntimeError:
            pass
    return out


# Long enough to clear rtst's 10-word minimum, which normalise() enforces before it will shape a
# request at all. The price does not depend on the prompt -- estimate-credits takes only model,
# duration, resolution, aspect and audio -- so a placeholder yields the real number.
QUOTE_PROMPT = ("a quote only placeholder prompt with enough words in it to satisfy the minimum "
                "prompt length this provider requires before pricing anything at all")


def public_job(job: dict) -> dict:
    """The wire shape. Keys starting with "_" are internal (the normalised provider params) and are
    stripped; nothing else is renamed, including `flow_status`, because the filmmaking app's client
    reads it today and a rename would break a working caller for cosmetic reasons."""
    out = {k: v for k, v in job.items() if not k.startswith("_")}
    if job.get("status") == "succeeded":
        out["content_url"] = f"/v1/videos/{job['id']}/content"
        out["content_urls"] = [f"/v1/videos/{job['id']}/content?index={i}"
                               for i in range(len(job.get("files") or []))]
    return out


# --------------------------------------------------------------------------- http plumbing


class Base(BaseHTTPRequestHandler):
    server_version = "VideoRouter/1.0"
    token: str | None = None
    # StreamRequestHandler applies this to the connection socket. Without it a client that opens a
    # socket, announces a Content-Length and then stops sending pins a worker thread forever.
    timeout = 60
    # A ComfyUI workflow is a few KB. Reading an arbitrary client-declared length into memory on a
    # process that is meant to sit on localhost forever is not worth the generality.
    MAX_BODY = 1 << 20

    def log_message(self, fmt, *args):        # quieter than the stdlib default, and scrubbed
        log(f"{self.address_string()} {scrub(fmt % args)}")

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, indent=1, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str) -> None:
        self._json(code, {"error": {"code": code, "message": scrub(msg)}})

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

        The job record's recorded absolute path is tried FIRST and is authoritative: the router wrote
        that path itself, so it needs no guessing about which provider's directory the clip landed in.
        Only if there is no record does it fall back to a bare id, which is looked up across EVERY
        registered out dir -- Flow's alone would 404 every rtst clip.

        A job can own several medias (Flow bills for all of them), so a job id plus an index selects
        one of them; a media id addresses itself and ignores the index.
        """
        ident = (ident or "").strip()
        if not ident:
            return None

        def recorded(job: dict, i: int) -> pathlib.Path | None:
            files = job.get("files") or ([job["file"]] if job.get("file") else [])
            if 0 <= i < len(files):
                p = _contained(pathlib.Path(files[i]))    # still containment-checked: the log is
                if p and p.exists():                      # data on disk, not a trusted input
                    return p
            return None

        job = STORE.get(ident)
        media_id = None
        if job:
            hit = recorded(job, index)
            if hit:
                return hit
            ids = job.get("media_ids") or ([job["media_id"]] if job.get("media_id") else [])
            if 0 <= index < len(ids):
                media_id = ids[index]
        if not media_id:
            media_id = ident[:-4] if ident.lower().endswith(".mp4") else ident
        # Charset guard: no "/", "\", "." or ":" can survive it, so no id can name a path. There is
        # deliberately no length floor -- rtst ids are 5 characters (measured: 96089).
        if not MEDIA_ID_RE.match(media_id):
            return None
        by_media = STORE.by_media(media_id)
        if by_media:
            ids = by_media.get("media_ids") or []
            hit = recorded(by_media, ids.index(media_id) if media_id in ids else 0)
            if hit:
                return hit
        for d in vp.out_dirs():
            p = _contained(pathlib.Path(d) / f"{media_id}.mp4")
            if p and p.exists():
                return p
        return None


# --------------------------------------------------------------------------- direct face


class DirectHandler(Base):
    """The face the filmmaking app should use. Honest content types, honest errors, every provider."""

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path.rstrip("/") or "/", urllib.parse.parse_qs(u.query)
        if path in ("/", "/healthz"):
            # Reachable without a token so a liveness probe keeps working, but only in redacted form:
            # the full shape carries account emails, project ids, balances, upstream error text and
            # the remembered tab URL -- which names the Flow project.
            #
            # `providers` is behind the token too, and so is each account's `provider` (withheld by
            # Account.public(redact=True)). Redacting one without the other would be theatre: with two
            # adapters registered, a global list of provider names plus a per-account port is enough to
            # infer which paid service each account belongs to. A liveness probe needs "ok"; it does
            # not need to know which video vendors this machine holds credentials for.
            authed = self._authed()
            return self._json(200, {
                "ok": DRY_RUN or any(a.ready for a in FLEET.accounts),
                "dry_run": DRY_RUN,
                "authenticated": authed,
                "providers": sorted(vp.REGISTRY) if authed else None,
                "accounts": [a.public(redact=not authed) for a in FLEET.accounts],
                "jobs": STORE.stats(),
                "self_heal": FLEET.self_heal,
                "heal": FLEET.heal_stats if authed else None,
                "measured_cost": (vp.MEASURED_COST or {"(none yet)": None}) if authed else None,
            })
        if not self._authed():
            return self._err(401, "bad or missing bearer token")
        if path == "/v1/accounts":
            if q.get("refresh"):
                FLEET.probe_all()
            return self._json(200, {"accounts": [a.public() for a in FLEET.accounts]})
        if path == "/v1/providers":
            return self._json(200, {"data": [
                {"provider": p.name, "title": p.title, "out_dir": str(p.out_dir),
                 "quotes_before_spending": bool(p.quotes_before_spending),
                 "max_spend_default": p.max_spend_default, "models": p.listing(),
                 "accounts": [a.label for a in FLEET.accounts if a.provider == p.name]}
                for p in vp.REGISTRY.values()]})
        if path == "/v1/models":
            # Every name a caller may use, across every provider, with the honesty flags the adapters
            # supply: `proven` says whether that key was ever exercised end to end, and
            # `quotes_before_spending` says whether est_cost is a price or a guess.
            data = []
            for p in vp.REGISTRY.values():
                for name in p.listing():
                    key = p.owns(name) or name
                    d = p.describe(key)
                    d["id"] = name
                    data.append(d)
            return self._json(200, {"data": data})
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

    # Every number is parsed BEFORE start_job. Parsing them after it means a typo in wait_timeout
    # raises inside the handler while the worker thread is already spending credits, and the caller
    # never even learns the job id.
    @staticmethod
    def _num(b, field, default, lo, hi, cast=int):
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

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        if path not in ("/v1/videos/generations", "/v1/videos/quote"):
            return self._err(404, f"no route for {u.path}")
        if not self._authed():
            return self._err(401, "bad or missing bearer token")
        b = self._body()
        if b is None:
            return self._err(400, "body must be a JSON object under 1 MiB")

        if path == "/v1/videos/quote":
            # Free and read-only: no job, no account held beyond the read, nothing spent. This is the
            # route a caller should use before committing to a generation.
            return self._json(200, quote_once(b.get("model"), b, b.get("account")))

        # Aspect, resolution, duration and size are NOT validated here: each provider owns its own
        # enums (Flow's two aspects and two resolutions are not rtst's per-model duration and quality
        # lists), and a router that policed both would encode one provider's rules as universal.
        seed, err = self._num(b, "seed", None, 0, 2 ** 32 - 1)
        if err:
            return self._err(400, err)
        budget, err = self._num(b, "budget", 600, 30, 3600)
        if err:
            return self._err(400, err)
        wait_timeout, err = self._num(b, "wait_timeout", 600, 1, 3600, float)
        if err:
            return self._err(400, err)
        max_spend, err = self._num(b, "max_spend", None, 1, 10 ** 6)
        if err:
            return self._err(400, err)

        job, err = start_job(prompt=b.get("prompt"), model_name=b.get("model"),
                             req={**b, "seed": seed}, requested_account=b.get("account"),
                             face="direct", budget=budget, max_spend=max_spend)
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

    Which provider a ckpt_name lands on is a registry fact -- whichever adapter claims that alias.
    Both of OmniRoute's registered ids are Flow's today; moving "svd-xt" into
    video_provider_rtst.aliases re-points it at rtst without touching this file.
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
            return self._json(200, {"system": {"comfyui_version": "video-router",
                                               "python_version": sys.version.split()[0]},
                                    "devices": []})
        if path == "/queue":
            # Counts, not ids. A job id here is a capability: it opens /history/{id}, which names the
            # media file, which /view then hands over as bytes the operator paid for.
            st = STORE.stats()
            return self._json(200, {"queue_running": [], "queue_pending": [],
                                    "video_router": {"running": st["active"], "total": st["total"],
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

        # Geometry is translated by whichever provider owns this ckpt: Flow turns pixels into two
        # enums, rtst into a short-edge quality number. Resolved here so a bad ckpt is a 400 rather
        # than an exception inside start_job.
        prov, key, err = vp.resolve_model(ckpt)
        if err or prov is None:
            return self._err(400, err or f"unknown ckpt_name {ckpt!r}")
        geo = prov.geometry(latent.get("width"), latent.get("height"))

        seed = sampler.get("seed")
        if isinstance(seed, int):
            seed = seed % 100000        # ComfyUI seeds are 32-bit; Flow's observed seeds are small
        else:
            seed = None

        # Deadlines sized to OmniRoute's 300s window, not the direct face's 600s+900s. Waiting 900s
        # for a free account, then rendering for 600s, guarantees OmniRoute has already given up --
        # so the credits would be spent on a video it can never fetch.
        req = {"aspect_ratio": geo.get("aspect"), "resolution": geo.get("resolution"), "seed": seed}
        job, err = start_job(prompt=prompt, model_name=ckpt, req=req, requested_account=None,
                             face="comfyui", budget=COMFY_BUDGET,
                             acquire_timeout=COMFY_ACQUIRE_TIMEOUT)
        if err:
            return self._err(400, err)
        log(f"{job['id'][:8]} comfyui face: ckpt={ckpt!r} -> {prov.name}/{key} "
            f"{geo.get('resolution')} {geo.get('aspect')} "
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
    FLEET.self_heal = not bool(a.no_self_heal)

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

    log(f"providers: {', '.join(f'{p.name} ({p.title})' for p in vp.REGISTRY.values())}")
    if DRY_RUN:
        log("DRY RUN: no provider call will be made and no credits spent; cached bytes are served")
        log(f"  stand-in media: {_dry_media() or 'NONE CACHED -- jobs will fail'}")
    else:
        log("probing accounts...")
        FLEET.probe_all()
        for acct in FLEET.accounts:
            mark = "ok " if acct.ready else "DOWN"
            log(f"  [{mark}] {acct.provider}/{acct.label:<12} port {acct.port}  "
                f"{acct.email or '-'}  credits={acct.credits}  "
                f"{'' if acct.ready else acct.reason}")
        if not any(x.ready for x in FLEET.accounts):
            log(f"no account is ready -- serving anyway; run "
                f"`python {pathlib.Path(__file__).name} doctor` to see why")
        if FLEET.self_heal:
            log(f"self-heal ON: a closed Chrome or a missing tab is relaunched/reopened during the "
                f"{FLEET.REFRESH_EVERY}s refresh (never a signed-out account, never a busy one)")
            FLEET.heal()
        else:
            log("self-heal OFF (--no-self-heal): down accounts are reported and left alone")
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
    log(f"                    (free price check first: POST /v1/videos/quote)")
    # Which provider a ckpt lands on is a registry fact, so print what it actually resolves to today
    # rather than a comment that can drift out of date.
    for mid in ("animatediff", "svd-xt"):
        p, k, err = vp.resolve_model(mid)
        log(f"OmniRoute       ->  comfyui ckpt {mid!r} -> "
            + (f"{p.name}/{k}" if p else f"UNRESOLVED ({err})"))
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
    print(f"{'provider':<8} {'label':<14} {'port':>5}  {'email':<30} {'credits':>8}  "
          f"{'tier':<14} status")
    for x in FLEET.accounts:
        print(f"{x.provider:<8} {x.label:<14} {x.port:>5}  {(x.email or '-'):<30} "
              f"{str(x.credits):>8}  {(x.tier or '-'):<14} {'ok' if x.ready else x.reason}")
    print()
    for p in vp.REGISTRY.values():
        mine = [x for x in FLEET.accounts if x.provider == p.name]
        ready = [x for x in mine if x.ready]
        total = sum(x.credits or 0 for x in ready)
        if not mine:
            print(f"{p.name:<8} no accounts registered -- any model of its would fail at submit "
                  f"time; register one with `add --provider {p.name} --port <port>`")
            continue
        # Capacity is reported through the SAME estimate() the router reserves with, so this line
        # cannot flatter the thing that actually gates a job. describe() prices the cheapest allowed
        # duration at the cheapest allowed quality, per model, and the cheapest of those is the most
        # clips this balance can possibly buy.
        #
        # For rtst that is now exact: price is a measured per-second rate x duration, so 24 credits
        # really is 4 vidu 3s @540p clips. (It is deliberately NOT the old flat floor of 2, which
        # would have claimed 12.) For Flow, which has no quote endpoint, est_cost is the reservation
        # floor -- the best price knowledge that exists for it -- and it is labelled as such.
        keys = {k for k in (vp.resolve_model(n)[1] for n in p.listing()) if k}
        cheapest, of, dims = None, None, ""
        for key in sorted(keys):
            try:
                d = p.describe(key)
            except vp.NON_FATAL:
                continue
            c = d.get("est_cost")
            if not (isinstance(c, int) and c > 0) or (cheapest is not None and c >= cheapest):
                continue
            durs, res = d.get("durations") or [], d.get("resolutions") or []
            cheapest, of = c, key
            # rtst advertises durations and bare quality numbers; Flow advertises one fixed
            # length_seconds and resolutions that already carry the "p". Print either without
            # inventing a second p or a duration Flow does not let a caller choose.
            secs = durs[0] if durs else d.get("length_seconds")
            qual = str(res[0]) if res else ""
            dims = ((f" {secs}s" if secs else "")
                    + (f" @{qual}" + ("" if qual.endswith("p") else "p") if qual else ""))
        measured = [v for k, v in vp.MEASURED_COST.items() if k.startswith(f"{p.name}/")]
        head = f"{p.name:<8} {total} credits across {len(ready)}/{len(mine)} ready account(s)"
        if cheapest:
            how = ("exact -- `quote --model <name>` re-checks it for free before every submit"
                   if p.quotes_before_spending else
                   f"the {'measured' if measured else 'estimated'} reservation floor; "
                   f"{p.name} cannot be quoted")
            print(f"{head}  ~= {total // cheapest} x its cheapest clip "
                  f"({of}{dims} = {cheapest})  -- {how}")
        else:
            print(f"{head}  -- no model on the menu could be priced (catalogue unavailable?)")
    print()
    print(f"registry: {ACCOUNTS_FILE}")
    return 0 if any(x.ready for x in FLEET.accounts) else 1


def cmd_add(a) -> int:
    prov = vp.get(a.provider)
    if prov is None:
        print(f"unknown provider {a.provider!r}; known: {', '.join(sorted(vp.REGISTRY))}")
        return 1
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if ACCOUNTS_FILE.exists():
        raw = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    else:
        raw = _migrate() or {"_note": REGISTRY_NOTE, "accounts": []}
    existing = raw.setdefault("accounts", [])
    label = a.label or f"{prov.name}-{a.port}"
    # The dup check is on (provider, port), NOT on port: one Chrome on 9222 legitimately carries both
    # a Flow tab and an rtst tab, and refusing the second would make the whole point unreachable.
    for x in existing:
        if not isinstance(x, dict):
            continue
        e = _entry(x)
        if e["provider"] == prov.name and e["port"] == int(a.port):
            print(f"{prov.name} on port {a.port} is already registered as {e['label']!r}")
            return 1
        if e["label"] == label:
            print(f"label {label!r} is already taken (by {e['provider']} on port {e['port']})")
            return 1
    entry = _entry({"label": label, "provider": prov.name, "port": a.port,
                    "profile": a.profile, "enabled": True,
                    "url": a.url or prov.default_url})
    existing.append(entry)
    raw.setdefault("_note", REGISTRY_NOTE)
    ACCOUNTS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"added {entry['provider']}/{entry['label']} port {entry['port']} "
          f"profile {entry['profile']} -> {ACCOUNTS_FILE}")
    print(f"  url: {entry['url']}")
    if not a.url:
        print(f"  NOTE: that is {prov.name}'s generic entry URL. It is overwritten with the real "
              f"one the first time a probe succeeds"
              + ("; Flow's project id lives ONLY in the tab URL, so a heal before that first "
                 "successful probe can only reopen the generic page."
                 if prov.name == "flow" else "."))
    print(f"  next: python {pathlib.Path(__file__).name} doctor")
    return 0


def cmd_doctor(a) -> int:
    """Walk every provider's own chain per account and name the first broken link.

    This is the answer to 'what do I do when it stops working': each provider tests its own
    dependencies in the order it actually uses them, and each failure prints the specific repair.
    The chains are generators, so nothing above a broken rung is tested -- testing it anyway
    produces confusing output.
    """
    global FLEET
    FLEET = load_accounts()
    bad = 0
    for acct in FLEET.accounts:
        prov = provider_of(acct)
        print("=" * 78)
        print(f"{acct.provider}/{acct.label}  (port {acct.port}, profile {acct.profile})")
        print("=" * 78)
        if prov is None:
            print(f"  [FAIL] {'provider adapter':<26} no adapter named {acct.provider!r}")
            print(f"\n  FIX: known providers are {', '.join(sorted(vp.REGISTRY))}. Fix the "
                  f"\"provider\" field for this entry in {ACCOUNTS_FILE}.\n")
            bad += 1
            continue
        if not acct.enabled:
            print(f"  [....] {'disabled in the registry':<26} skipped")
            print()
            continue
        failed = None
        try:
            for st in prov.doctor_chain(acct, deep=bool(a.deep)):
                print(f"  [{'ok ' if st.ok else 'FAIL'}] {st.name:<26} {scrub(st.detail)}")
                if not st.ok:
                    failed = st
                    break
        except NON_FATAL as e:
            print(f"  [FAIL] {'chain raised':<26} {type(e).__name__}: {scrub(e)[:70]}")
            failed = vp.Step("chain raised", False, "", prov.recovery_hint("<id>"))
        if failed is not None:
            bad += 1
            if failed.fix:
                print(f"\n  FIX: {failed.fix}\n")
            else:
                print()
            continue
        print()
    print("=" * 78)
    if bad:
        print(f"  {bad} account(s) need attention -- see the FIX line under each.")
    else:
        n = sum(1 for x in FLEET.accounts if x.enabled)
        print(f"  All {n} enabled account(s) healthy end to end"
              + ("" if a.deep else "; add --deep to also prove each provider's submit gate "
                                   "still accepts us (still 0 credits)"))
    print("=" * 78)
    return 1 if bad else 0


def cmd_wake(a) -> int:
    """Recover the fleet after Chrome was closed or a tab was lost.

    Same body the refresh loop runs, so what `wake` fixes is exactly what `serve` fixes by itself.
    Navigation only -- nothing is clicked and no generate button is touched -- so waking cannot
    spend a credit. --dry-run prints the launch and tab plan without acting.
    """
    global FLEET
    FLEET = load_accounts()
    log("probing before healing (heal decisions key off the structured fault, not off prose)")
    FLEET.probe_all()
    down = [x for x in FLEET.accounts if x.enabled and not x.ready]
    for x in FLEET.accounts:
        log(f"  [{'ok ' if x.ready else 'DOWN'}] {x.provider}/{x.label:<12} port {x.port}  "
            f"fault={x.fault or '-'}  {'' if x.ready else x.reason}")
    if not down:
        log("nothing to heal: every enabled account is ready")
        return 0
    actions = FLEET.heal(dry_run=bool(a.dry_run))
    if not actions:
        log("no heal-able account: every down account is signed out, refused or busy")
        return 1
    if a.dry_run:
        log("dry run: nothing was launched, opened or probed")
        return 0
    still = [x for x in FLEET.accounts if x.enabled and not x.ready]
    log(f"healed {len(down) - len(still)}/{len(down)}; heal counters {FLEET.heal_stats}")
    for x in still:
        log(f"  still down: {x.provider}/{x.label}: {x.reason}")
    return 1 if still else 0


def cmd_quote(a) -> int:
    """A price, for free, through the reserved account's own tab. Spends nothing.

    Deliberately reports `exact: false` for a provider that cannot be quoted rather than dressing an
    estimate up as a price -- that distinction is the whole reason estimate() and confirm() are
    separate calls.
    """
    global FLEET
    FLEET = load_accounts()
    FLEET.probe_all()
    req = {"duration": a.duration, "resolution": a.resolution, "aspect_ratio": a.aspect,
           "size": a.size, "audio": a.audio, "prompt": a.prompt}
    out = quote_once(a.model, {k: v for k, v in req.items() if v is not None}, a.account)
    print(json.dumps(out, indent=2, default=str))
    if out.get("error"):
        return 1
    q, est = out.get("quote"), out.get("estimate")
    if out.get("exact"):
        print(f"\n{out['provider']}/{out['model']}: {q} credits, quoted exactly by the provider "
              f"(balance {out.get('balance')}, per-job ceiling {out.get('max_spend_default')})")
    else:
        print(f"\n{out['provider']}/{out['model']}: ~{est} credits ESTIMATED -- {out['provider']} "
              f"has no quote endpoint, so this is the reservation floor and the provider's own "
              f"balance check is the only real gate")
    return 0


def cmd_models(a) -> int:
    """Every name a caller may use, per provider, with the honesty flags attached."""
    for p in vp.REGISTRY.values():
        print("=" * 78)
        print(f"{p.name}  --  {p.title}")
        print(f"  quotes before spending: {p.quotes_before_spending}   "
              f"default per-job ceiling: {p.max_spend_default}   out dir: {p.out_dir}")
        print("=" * 78)
        try:
            names = p.listing()
        except NON_FATAL as e:
            print(f"  could not list models: {type(e).__name__}: {scrub(e)[:80]}")
            continue
        for name in names:
            key = p.owns(name) or name
            d = p.describe(key)
            note = d.get("note")
            print(f"  {name:<26} -> {key:<24} {'proven' if d.get('proven') else 'INFERRED'}"
                  + (f"  ({note})" if note and not d.get("proven") else ""))
        print()
    print(f"default model: {vp.DEFAULT_MODEL}")
    print("a bare name is searched across every provider; \"rtst/vidu\" pins the provider")
    return 0


# --------------------------------------------------------------------------- fresh machine


def _free_label(entries: list, stem: str) -> str:
    """A label no existing entry has taken. Labels are how the operator names an account in every
    other command, so a collision here would make one of the two unaddressable."""
    taken = {_entry(x)["label"] for x in entries if isinstance(x, dict)}
    for n in range(1, 100):
        cand = f"{stem}-{n}"
        if cand not in taken:
            return cand
    return f"{stem}-{uuid.uuid4().hex[:6]}"


def cmd_setup(a) -> int:
    """One guided pass from a clean machine to a green doctor.

    Every step is idempotent -- run it again after a reboot, after adding a provider, or whenever you
    are not sure what state the machine is in. It will not re-register, re-launch or re-sign anything
    that is already good.

    The one step that cannot be automated is the sign-in. No password is ever typed by this process
    (that is chrome_live_guard's rule, and the reason FAULT_AUTH is excluded from self-heal), so setup
    opens the provider's page, waits for you, and then proves the result by probing.
    """
    ok = True
    name = pathlib.Path(__file__).name
    print("=" * 78)
    print("video_router setup -- clean machine to green doctor")
    print("=" * 78)

    print("\n[1/5] preflight")
    print(f"  python         {sys.version.split()[0]}  {sys.executable}")
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists() and pathlib.Path(sys.executable).resolve() != venv_py.resolve():
        # Every *_task.bat in this directory runs the venv interpreter. If setup registers accounts
        # under one interpreter and the scheduled task serves them under another, the two can disagree
        # about installed packages while both look fine in isolation.
        print(f"  NOTE           this repo's scheduled tasks all run {venv_py}")
        print(f"                 consider re-running setup with that interpreter")
    try:
        print(f"  chrome         {find_chrome()}")
    except RuntimeError as e:
        print(f"  chrome         NOT FOUND -- {e}")
        ok = False
    for d in [STATE, STATE / "automation_profiles", *vp.out_dirs()]:
        try:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  dir ready      {d}")
        except OSError as e:
            print(f"  dir FAILED     {d}: {type(e).__name__}: {e}")
            ok = False

    print(f"\n[2/5] registry -- {ACCOUNTS_FILE}")
    if not vp.REGISTRY:
        print("  no provider adapter is registered; nothing to set up")
        return 1
    raw = (json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8")) if ACCOUNTS_FILE.exists()
           else (_migrate() or {"_note": REGISTRY_NOTE, "accounts": []}))
    entries = raw.setdefault("accounts", [])
    have = {(_entry(x)["provider"], _entry(x)["port"])
            for x in entries if isinstance(x, dict)}
    added = 0
    for pname in sorted(vp.REGISTRY):
        prov = vp.get(pname)
        if (pname, int(a.port)) in have:
            print(f"  already there  {pname} on port {a.port}")
            continue
        entries.append(_entry({"label": _free_label(entries, pname), "provider": pname,
                               "port": a.port, "profile": a.profile, "enabled": True,
                               "url": prov.default_url}))
        added += 1
        print(f"  registered     {pname} on port {a.port} -> {prov.default_url}")
    if added:
        raw.setdefault("_note", REGISTRY_NOTE)
        ACCOUNTS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        print(f"  wrote          {added} new entry(s)")

    fleet = load_accounts()
    print(f"\n[3/5] chrome -- one per port, on its own profile dir")
    for port in sorted({x.port for x in fleet.accounts}):
        if fleet._port_alive(port):
            print(f"  port {port}     already answering")
            continue
        acct = next(x for x in fleet.accounts if x.port == port)
        launched, detail = fleet._launch_chrome(acct)
        print(f"  port {port}     {'launched' if launched else 'FAILED'}: {detail}")
        ok = ok and launched

    print(f"\n[4/5] sign-in -- once per provider, by hand, on purpose")
    for acct in fleet.accounts:
        prov = provider_of(acct)
        fleet.probe(acct)
        if acct.ready:
            print(f"  {acct.provider}/{acct.label}: signed in, {acct.credits} credits")
            continue
        opened, detail = fleet._open_tab(acct)
        print(f"  {acct.provider}/{acct.label}: not ready -- {acct.reason}")
        print(f"      opened {prov.title}: {detail}")
        if a.no_input:
            print(f"      --no-input: sign in, then re-run `python {name} setup`")
            ok = False
            continue
        for _ in range(3):
            try:
                input(f"      sign in to {prov.title} in that window, then press Enter... ")
            except (EOFError, KeyboardInterrupt):
                print("\n      skipped")
                break
            fleet.probe(acct)
            if acct.ready:
                print(f"      now ready: {acct.credits} credits")
                break
            print(f"      still not ready: {acct.reason}")
        ok = ok and acct.ready

    print(f"\n[5/5] proof -- the same doctor you would run any other day")
    rc = cmd_doctor(argparse.Namespace(deep=False))
    if rc == 0 and ok:
        print(f"\nsetup complete. Next:")
        print(f"  python {name} serve            # run it now, in this window")
        print(f"  python {name} boot --install   # and/or start it at boot, unattended")
        return 0
    print(f"\nsetup did NOT finish clean -- fix what doctor named above and re-run "
          f"`python {name} setup`")
    return 1


TASK_BAT = pathlib.Path(__file__).with_name("video_router_task.bat")
SERVE_LOG = STATE / "video_router_serve.log"
TASK_KEEP = "OmniRoute Video Router (keepalive)"
STARTUP_DIR = (pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home()))
               / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
STARTUP_VBS = STARTUP_DIR / "omniroute_video_router.vbs"


def _startup_vbs_text() -> str:
    """The logon trigger, as a hidden-window .vbs in the per-user Startup folder.

    MEASURED 2026-08-24: `schtasks /Create /SC ONLOGON` answers "Access is denied." from a normal
    prompt -- an ONLOGON trigger can name any user on the box, so Windows reserves it for an
    administrator. The Startup folder needs no elevation, is per-user by construction, and runs
    inside the user's own desktop session, which is exactly the property `serve` needs. This repo
    already starts oauth_keepalive.py the same way, so this follows that file's shape: Run(cmd, 0,
    False) means hidden window, do not wait.
    """
    return ('Set WshShell = CreateObject("WScript.Shell")\r\n'
            f'WshShell.Run """{TASK_BAT}""", 0, False\r\n')


def _task_bat_text() -> str:
    """The Task Scheduler wrapper, in the same shape as every other *_task.bat in this directory.

    Two things it has to get right. It runs the repo's own .venv interpreter, like its siblings. And it
    exits quietly if the direct port already answers, so the 5-minute keepalive trigger acts as a
    supervisor rather than a second server -- belt and braces over Task Scheduler's IgnoreNew policy.
    """
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():                      # a machine that never made the venv still gets a wrapper
        py = pathlib.Path(sys.executable)
    return (
        "@echo off\r\n"
        "rem OmniRoute Video Router -- invoked by Windows Task Scheduler at logon and every 5 min.\r\n"
        f"rem Starts the two video faces if :{DIRECT_PORT} is not already answering.\r\n"
        f"rem Written by `python {pathlib.Path(__file__).name} boot --install`; edit that, not this.\r\n"
        f"cd /d {ROOT}\r\n"
        f'"{py}" -c "import urllib.request;urllib.request.urlopen('
        f"'http://127.0.0.1:{DIRECT_PORT}/healthz',timeout=3)\" >nul 2>&1\r\n"
        "if not errorlevel 1 exit /b 0\r\n"
        f'"{py}" -u "{pathlib.Path(__file__)}" serve >> "{SERVE_LOG}" 2>&1\r\n')


def _schtasks_cmds() -> list[list[str]]:
    # /IT is not stylistic: the providers are driven through a real Chrome window, so the server needs
    # an interactive desktop session to heal into. A task running in session 0 would relaunch Chrome
    # somewhere nobody can ever sign in. The logon half of the job is the Startup .vbs above -- see
    # _startup_vbs_text for why it is not a second schtasks entry.
    return [
        ["schtasks", "/Create", "/F", "/IT", "/TN", TASK_KEEP, "/TR", str(TASK_BAT),
         "/SC", "MINUTE", "/MO", "5"],
    ]


def cmd_boot(a) -> int:
    """Register (or just print) the two things that keep `serve` running without a human.

    A Startup-folder .vbs for "start at logon" and a 5-minute schtasks entry for "and keep it
    started". Prints the plan and changes nothing unless asked -- the same dry-run-first habit as
    `wake`.
    """
    name = pathlib.Path(__file__).name
    if a.remove:
        if STARTUP_VBS.exists():
            STARTUP_VBS.unlink()
            print(f"  removed   {STARTUP_VBS}")
        else:
            print(f"  absent    {STARTUP_VBS}")
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_KEEP],
                           capture_output=True, text=True)
        ok = r.returncode == 0
        print(f"  {'removed  ' if ok else 'not removed'} {TASK_KEEP}"
              f"{'' if ok else ': ' + (r.stderr or r.stdout).strip()[:120]}")
        print(f"\n{TASK_BAT.name} was left in place; delete it by hand if you want it gone.")
        print("A serve already running is untouched -- Ctrl-C it, or just leave it.")
        return 0

    if not a.install:
        print(f"would write {TASK_BAT}:\n")
        for line in _task_bat_text().splitlines():
            print("    " + line)
        print(f"\nwould write {STARTUP_VBS}:\n")
        for line in _startup_vbs_text().splitlines():
            print("    " + line)
        print("\nwould register:\n")
        for c in _schtasks_cmds():
            print("    " + subprocess.list2cmdline(c))
        print(f"\n  {STARTUP_VBS.name:<34} starts it when you log on")
        print(f"  {TASK_KEEP:<34} restarts it within 5 min if it ever dies")
        print("\nserve drives real Chrome windows, so it needs an interactive desktop session: a task")
        print("in session 0 would relaunch Chrome where nobody can ever sign in. That is why the logon")
        print("trigger is a Startup-folder .vbs and not ONSTART -- if this box reboots to a locked")
        print("login screen the router waits for a human to log on, and no scheduling trick gets")
        print("around that. (ONLOGON via schtasks would need an elevated prompt; the Startup folder")
        print("does not, and this repo already starts oauth_keepalive.py that way.)")
        print("\nnothing was changed. Re-run with --install to do it.")
        return 0

    TASK_BAT.write_text(_task_bat_text(), encoding="utf-8")
    print(f"wrote {TASK_BAT}")
    SERVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    rc = 0
    try:
        STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        STARTUP_VBS.write_text(_startup_vbs_text(), encoding="utf-8")
        print(f"wrote {STARTUP_VBS}")
    except Exception as e:                                                   # noqa: BLE001
        rc = 1
        print(f"  FAILED       {STARTUP_VBS}: {type(e).__name__}: {e}")
    for c in _schtasks_cmds():
        r = subprocess.run(c, capture_output=True, text=True)
        tn = c[c.index("/TN") + 1]
        if r.returncode == 0:
            print(f"  registered   {tn}")
        else:
            rc = 1
            print(f"  FAILED       {tn}: {(r.stderr or r.stdout).strip()[:200]}")
    if rc:
        print(f"\nSomething above was refused. `python {name} boot` prints the exact commands and file")
        print("contents if you would rather place them by hand from an elevated prompt.")
        return rc
    print("\nserve now starts when you log on, and is restarted within 5 min if it dies.")
    print(f"  log:     {SERVE_LOG}")
    print(f'  check:   schtasks /Query /TN "{TASK_KEEP}"')
    print(f"  undo:    python {name} boot --remove")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run both faces over every provider")
    s.add_argument("--bind", default="127.0.0.1")
    s.add_argument("--direct-port", type=int, default=DIRECT_PORT)
    s.add_argument("--comfy-port", type=int, default=COMFY_PORT,
                   help="0 to disable the ComfyUI face")
    # FLOW_SHIM_TOKEN is still honoured: worklog #1064 documents it, and a rename that silently
    # dropped the operator's existing token would publish an unauthenticated face on their next run.
    s.add_argument("--token", default=(os.environ.get("VIDEO_ROUTER_TOKEN")
                                      or os.environ.get("FLOW_SHIM_TOKEN") or None),
                   help="require this bearer on the direct face")
    s.add_argument("--dry-run", action="store_true",
                   help="serve cached bytes instead of calling a provider; spends nothing")
    s.add_argument("--no-self-heal", action="store_true",
                   help="report down accounts instead of relaunching Chrome / reopening tabs")
    s.set_defaults(fn=serve)

    c = sub.add_parser("accounts", help="registry plus live balances, per provider")
    c.set_defaults(fn=cmd_accounts)

    d = sub.add_parser("add", help="register another provider tab / Chrome port")
    d.add_argument("--port", type=int, default=DEFAULT_PORT)
    d.add_argument("--provider", default="flow",
                   help=f"one of: {', '.join(sorted(vp.REGISTRY)) or '(none registered)'}")
    d.add_argument("--label", default="")
    d.add_argument("--profile", default=DEFAULT_PROFILE,
                   help="safe_profile_dir tag; each Chrome needs its OWN profile dir")
    d.add_argument("--url", default="",
                   help="tab URL to remember (defaults to the provider's entry page)")
    d.set_defaults(fn=cmd_add)

    o = sub.add_parser("doctor", help="find and explain the broken link, per provider")
    o.add_argument("--deep", action="store_true",
                   help="also prove each provider's submit gate still accepts us (0 credits)")
    o.set_defaults(fn=cmd_doctor)

    w = sub.add_parser("wake", help="relaunch closed Chromes and reopen missing tabs")
    w.add_argument("--dry-run", action="store_true",
                   help="print exactly what would be launched and opened, without acting")
    w.set_defaults(fn=cmd_wake)

    q = sub.add_parser("quote", help="free price check; spends nothing")
    q.add_argument("--model", default=vp.DEFAULT_MODEL)
    q.add_argument("--duration", type=int, default=None)
    q.add_argument("--resolution", default=None)
    q.add_argument("--aspect", default=None)
    q.add_argument("--size", default=None, help="WxH, translated to the provider's own params")
    q.add_argument("--audio", action="store_true", default=None)
    q.add_argument("--prompt", default=None, help="only affects providers that price per prompt")
    q.add_argument("--account", default=None)
    q.set_defaults(fn=cmd_quote)

    m = sub.add_parser("models", help="every usable model name, per provider")
    m.set_defaults(fn=cmd_models)

    u = sub.add_parser("setup", help="clean machine -> green doctor, one guided idempotent pass")
    u.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help="the Chrome debug port every provider's tab lives on")
    u.add_argument("--profile", default=DEFAULT_PROFILE,
                   help="safe_profile_dir tag; each Chrome PORT needs its own profile dir")
    u.add_argument("--no-input", action="store_true",
                   help="never wait at a sign-in prompt; report what is missing and exit non-zero")
    u.set_defaults(fn=cmd_setup)

    b = sub.add_parser("boot", help="keep serve running across logons and crashes (Task Scheduler)")
    b.add_argument("--install", action="store_true", help="actually write the wrapper and register")
    b.add_argument("--remove", action="store_true", help="delete both scheduled tasks")
    b.set_defaults(fn=cmd_boot)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {scrub(exc)[:500]}")
        if os.environ.get("VIDEO_ROUTER_TRACE") or os.environ.get("FLOW_SHIM_TRACE"):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
