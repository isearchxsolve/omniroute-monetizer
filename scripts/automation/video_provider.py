"""video_provider.py -- the seam every video provider plugs into.

WHY THIS EXISTS: flow_shim.py grew a working rotation engine (highest-balance-first account
selection, a reservation floor, a lock held across submit+poll, an append-only job log, two HTTP
faces) and welded all of it to Google Flow. rtst.ai then proved out as a second real route with its
own one-shot CLI. Duplicating the engine per provider is not an option -- two processes cannot both
bind :8188, and a money bug fixed in one copy would live on in the other -- so the engine stays
singular in video_router.py and everything provider-shaped moves behind this interface.

THE TWO ASYMMETRIES THIS INTERFACE EXISTS TO EXPRESS HONESTLY
  * COST. rtst answers GET /video/estimate-credits for free and exactly; Flow cannot be quoted at
    all and had its price learned by spending 20 credits and diffing the balance. So the money path
    is split in two: estimate() is account-independent and only decides WHICH account is big enough,
    while confirm() runs on the already-reserved account and may refuse before anything is spent.
    rtst's confirm() is a real pre-commit gate. Flow's cannot be, and says so rather than pretending.
  * FAN-OUT. One Flow submit returns a LIST of medias and bills for every one of them; one rtst
    submit returns exactly one id. The job record was already plural, so rtst returns a 1-element
    list and no wire field changes shape.

FAULTS ARE STRUCTURED, NOT PROSE. probe() sets acct.fault to one of FAULT_*, because the self-heal
in video_router keys off it. Regexing a human-readable reason string to decide whether to launch a
browser is exactly the kind of thing that quietly starts launching browsers in a loop.
"""
from __future__ import annotations

import pathlib
import re
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Imported here once so there is exactly one fallback definition for the whole router. The guard is
# present in this repo; if it ever stops importing, that must be loud rather than silent, because
# without it a misconfigured port can attach to the operator's live Chrome and get their session
# revoked (see chrome_live_guard.py).
try:
    from chrome_live_guard import (LiveProfileRefused, assert_cdp_safe,  # noqa: F401
                                   assert_safe, is_refusal, live_devtools_ports, safe_profile_dir)
except Exception:  # pragma: no cover
    print("!! chrome_live_guard not importable -- live-profile protection is OFF", flush=True)

    class LiveProfileRefused(RuntimeError):
        pass

    def assert_cdp_safe(endpoint, who="video_router"):
        return endpoint

    def assert_safe(path, who="video_router"):
        return pathlib.Path(path)

    def is_refusal(exc):
        return False

    def live_devtools_ports():
        return set()

    def safe_profile_dir(tag="automation"):
        return pathlib.Path(__file__).resolve().parents[2] / "state" / "automation_profiles" / tag

# --------------------------------------------------------------------------- logging & secrets

# The union of googleflow_client.SECRET_RE and rtst_client.SECRET_RE, so anything logged through the
# router is scrubbed regardless of which provider produced it. Widened deliberately: a pattern that
# over-matches costs a redacted log line, one that under-matches leaks a live bearer.
SECRET_RE = re.compile(r"(ya29\.[\w\-.]+|AIza[\w\-]{10,}|1//[\w\-.]{10,}|0[cC]A[\w\-]{40,}"
                       r"|eyJ[\w\-]{18,}|sk-[A-Za-z0-9]{20,}|Bearer\s+[\w\-.]{20,})")


def scrub(text) -> str:
    return SECRET_RE.sub("[REDACTED]", str(text))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {scrub(msg)}", flush=True)


# cdp.pick_page signals "no matching tab" by raising SystemExit, which `except Exception` does not
# catch. Uncaught in a worker thread it abandons a job whose credits are already spent; uncaught in
# the refresh loop it freezes every balance for the life of the process. A missing tab is a routine,
# recoverable condition here, so it is caught everywhere a browser is touched.
NON_FATAL = (Exception, SystemExit)

# --------------------------------------------------------------------------- faults

FAULT_NONE = None
FAULT_PORT = "port"          # the debug port is not answering: Chrome is closed. Relaunchable.
FAULT_TAB = "tab"            # port answers, no tab for this provider. Reopenable by navigation.
FAULT_AUTH = "auth"          # signed out / login wall. NOT heal-able: no password is ever typed.
FAULT_REFUSED = "refused"    # points at the operator's live Chrome. Never touched again.
FAULT_OTHER = "other"        # anything else; reported, not acted on.

HEALABLE = (FAULT_PORT, FAULT_TAB)

# --------------------------------------------------------------------------- the reservation floor

# A billing observation is credits_before (read from the account) minus credits_after (read from the
# submit response). Anything else spending on that same account in between -- the operator in their
# own browser, or a direct googleflow_client.py run -- lands inside that window, so the delta is our
# cost PLUS theirs. Letting the newest delta become the floor means one concurrent 1080p generation
# elsewhere raises the floor to 80 permanently, after which acquire() refuses every account holding
# 20-79 credits: capacity stranded by an arithmetic artefact, which is exactly what the old
# 60-credit floor did. So the floor moves DOWN freely and UP never, and disagreements are logged.
# Under-reserving is the safe direction: both providers enforce the balance server-side, so the cost
# of guessing low is one rejected submit, while guessing high is invisible lost capacity.
COST_FLOOR_MAX = 200          # a per-media delta above this is someone else's spending, not ours

# Keyed "<provider>/<model>". Unqualified keys would let rtst's 2-credit vidu floor collide with a
# Flow model of the same name and strand a 950-credit account.
MEASURED_COST: dict[str, int] = {}


def observe_cost(model: str, charged: int | None, media_count: int | None,
                 fallback: int = 20) -> None:
    """Fold one billing observation into the reservation floor. A genuine upstream price rise and a
    concurrent external spend are indistinguishable from here, so an increase is reported to the
    operator rather than acted on."""
    if not isinstance(charged, int) or charged <= 0:
        return
    per = charged // media_count if isinstance(media_count, int) and media_count > 0 else charged
    if per <= 0 or per > COST_FLOOR_MAX:
        log(f"ignoring implausible billing observation for {model}: {charged} credits over "
            f"{media_count} media; floor stays {MEASURED_COST.get(model, fallback)}")
        return
    old = MEASURED_COST.get(model)
    if old is None or per < old:
        MEASURED_COST[model] = per
        if old is not None:
            log(f"reservation floor for {model} lowered {old} -> {per}/media")
    elif per > old:
        log(f"{model} charged {per}/media this run but the floor stays at {old}. If every run now "
            f"charges {per}, either the provider raised its price or something else is spending on "
            f"this account at the same time -- check before trusting the balance arithmetic")


# --------------------------------------------------------------------------- accounts


class Account:
    """One provider login == one browser tab == one balance.

    An account is identified by (provider, port, label), not by port alone: the Flow tab and the
    rtst tab live in the SAME Chrome profile on port 9222 and hold completely independent balances.
    A per-port lock would serialise two jobs that cannot collide; a per-account lock does not.
    """

    def __init__(self, provider: str, port: int, label: str = "", enabled: bool = True,
                 profile: str = "providers", url: str | None = None):
        self.provider = provider
        self.port = int(port)
        self.label = label or f"{provider}-{port}"
        self.enabled = bool(enabled)
        self.profile = profile or "providers"
        # The last URL this account was successfully probed on. This one field is what makes
        # recovery from a closed Chrome mechanical: Flow's project id exists ONLY in its tab URL
        # (FlowSession parses /project/<uuid> out of location.href), so reopening labs.google/fx
        # generically is not enough to restore a working account.
        self.url = url
        self.lock = threading.Lock()
        self.email: str | None = None
        self.project_id: str | None = None
        self.tier: str | None = None
        self.credits: int | None = None
        self.ready = False
        self.reason = "not probed yet"
        self.fault: str | None = FAULT_OTHER
        self.state: dict = {}          # adapter scratch space (cached session, model catalogue, ...)

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.label}"

    def public(self, redact: bool = False) -> dict:
        """redact=True is the pre-authentication shape: enough to see the fleet is alive, nothing
        that identifies an account. Emails, project ids, tiers, balances, the last-known URL (it
        names the Flow project) and the free-text `reason` (which can quote an upstream error
        verbatim) are all withheld until the caller authenticates."""
        d = {"label": self.label, "provider": self.provider, "port": self.port,
             "enabled": self.enabled, "ready": self.ready, "busy": self.lock.locked()}
        if redact:
            return d
        d.update(email=self.email, project_id=self.project_id, tier=self.tier,
                 credits=self.credits, reason=self.reason, fault=self.fault, url=self.url)
        return d


# --------------------------------------------------------------------------- doctor steps


class Step:
    """One rung of a provider's dependency chain, in the order it is actually used."""

    def __init__(self, name: str, ok: bool, detail: str = "", fix: str = ""):
        self.name, self.ok, self.detail, self.fix = name, bool(ok), detail, fix


# --------------------------------------------------------------------------- the interface


class Provider:
    """Everything the router needs to know about one video site.

    Subclasses must not import video_router: the dependency runs one way only, so an adapter can be
    exercised in a test without standing up an HTTP server.
    """

    name = "?"
    title = "?"
    tab_match = ""               # substring identifying this provider's tab
    default_url = ""             # where to navigate when no URL has been remembered yet
    out_dir: pathlib.Path = pathlib.Path(".")
    aliases: dict[str, str] = {}
    proven: set[str] = set()
    est_cost = 20                # floor used before anything has been measured
    max_spend_default: int | None = None
    quotes_before_spending = False   # True only if confirm() can refuse using a real upstream price

    # -- naming ------------------------------------------------------------------------------

    def owns(self, name: str) -> str | None:
        """Loose caller-supplied name -> this provider's model key, or None."""
        n = str(name).strip().lower()
        if n in self.aliases:
            return self.aliases[n]
        return n if n in set(self.aliases.values()) else None

    def model_note(self, key: str) -> str | None:
        return None if key in self.proven else "model key inferred, never exercised end to end"

    # -- request shaping ---------------------------------------------------------------------

    def normalise(self, req: dict) -> tuple[dict | None, str | None]:
        """Validated provider params, or an error string. Each provider owns its own enums: Flow's
        two aspects and two resolutions are not rtst's per-model duration and quality lists, and a
        router that tried to police both would end up encoding one provider's rules as universal."""
        raise NotImplementedError

    def geometry(self, width: int | None, height: int | None) -> dict:
        """ComfyUI speaks pixels. Every provider speaks something else."""
        raise NotImplementedError

    # -- money -------------------------------------------------------------------------------

    def estimate(self, params: dict) -> int:
        """Account-independent credit estimate. Feeds acquire(need=...) only -- it decides which
        account is big enough, never whether to spend."""
        raise NotImplementedError

    def confirm(self, acct: Account, params: dict,
                max_spend: int | None = None) -> tuple[int | None, str | None]:
        """Last gate before money moves, run on the RESERVED account. Returning an error aborts the
        job with nothing spent. Providers that cannot be quoted return their floor and no error.

        max_spend is the caller's per-job ceiling. A provider that can be quoted must enforce it
        against the REAL price; a provider that cannot can only check it against its floor, which is
        weaker and must not be dressed up as more.
        """
        est = self.estimate(params)
        if max_spend is not None and isinstance(est, int) and est > int(max_spend):
            return est, (f"estimated {est} credits exceeds max_spend {max_spend} "
                         f"(estimate only -- {self.name} cannot be quoted exactly)")
        return est, None

    # -- the job -----------------------------------------------------------------------------

    def probe(self, acct: Account) -> None:
        """Refresh readiness, balance and acct.url. Must never raise: an account being down is a
        state to report and route around, not an error that takes the server with it. Must set
        acct.fault so the self-heal can tell "Chrome is closed" from "this login is dead"."""
        raise NotImplementedError

    def submit(self, acct: Account, params: dict) -> dict:
        """Spend. Returns {items: [id, ...], credits_after: int|None, media_count, workflow_count}.

        MUST NOT retry internally on an HTTP status. Neither provider offers an idempotency key, so
        a retry after a submit that actually landed mints and charges a second video.
        """
        raise NotImplementedError

    def wait(self, acct: Account, item: str, budget: int, on_status) -> dict:
        """Poll one already-paid-for item to completion. Returns the provider's metadata dict.

        on_status takes exactly ONE argument: a short human-readable status line. The two upstream
        clients disagree here (googleflow_client.wait calls back with (status, elapsed), rtst prints
        instead of calling back), so the adapters absorb that difference and the router sees one shape.
        """
        raise NotImplementedError

    def duration_of(self, meta: dict) -> str | None:
        """Clip length as the provider reports it, for the job record. Best-effort by design: it is
        metadata, so a missing field must not fail a job whose credits are already spent."""
        return None

    def download(self, acct: Account, item: str, meta: dict | None = None) -> pathlib.Path:
        raise NotImplementedError

    # -- operator help -----------------------------------------------------------------------

    def describe(self, key: str) -> dict:
        """One model's advertised shape, for the router's model listing. Honest by construction: a
        key that was never exercised says so, and a provider that cannot be quoted says so."""
        return {"model": key, "provider": self.name, "title": self.title,
                "proven": key in self.proven, "note": self.model_note(key),
                "est_cost": self.estimate({"model": key}),
                "quotes_before_spending": bool(self.quotes_before_spending),
                "max_spend_default": self.max_spend_default}

    def doctor_chain(self, acct: Account, deep: bool = False):
        """Yield Steps in dependency order. A generator, not a list: once a rung fails there is no
        point testing the ones above it, and testing them anyway produces confusing output.

        deep=True may make extra upstream calls, but must still spend nothing.
        """
        raise NotImplementedError

    def recovery_hint(self, item: str) -> str:
        """The exact command that collects an already-paid-for clip later."""
        return f"(no recovery command registered for {self.name})"


# --------------------------------------------------------------------------- registry

REGISTRY: dict[str, Provider] = {}


def register(p: Provider) -> Provider:
    REGISTRY[p.name] = p
    return p


def get(name: str) -> Provider | None:
    return REGISTRY.get(str(name).strip().lower())


def out_dirs() -> list[pathlib.Path]:
    """Every directory a served video can legitimately live in. The router's file resolution
    containment-checks against this list; it is the traversal guard, not decoration."""
    return [p.out_dir for p in REGISTRY.values()]


DEFAULT_MODEL = "veo-3.1-fast"      # unchanged from flow_shim: a bare request still means Flow fast


def resolve_model(name: str | None) -> tuple[Provider | None, str | None, str | None]:
    """Loose name -> (provider, model key, error).

    Unknown names are rejected rather than defaulted: quietly generating a cheap fast clip for
    someone who asked for something else is a billing surprise, and quietly generating on the WRONG
    PROVIDER spends the wrong balance.

    A "prefix/name" string is accepted two ways. If the prefix names a registered provider
    ("rtst/vidu") it pins the search to that provider. Otherwise the prefix is discarded, which is
    what makes OmniRoute's "comfyui/veo-3.1-fast" work.
    """
    if not REGISTRY:
        return None, None, "no providers registered"
    raw = str(name or DEFAULT_MODEL).strip().lower()
    pool = list(REGISTRY.values())
    if "/" in raw:
        head, tail = raw.rsplit("/", 1)
        pinned = get(head.rsplit("/", 1)[-1])
        if pinned is not None:
            pool, raw = [pinned], tail
        else:
            raw = tail
    for p in pool:
        key = p.owns(raw)
        if key:
            return p, key, None
    known = ", ".join(sorted(f"{p.name}/{a}" for p in REGISTRY.values() for a in p.aliases))
    return None, None, f"unknown model {name!r}; try one of: {known}"


def pixels_to_aspect(width: int | None, height: int | None) -> str:
    """OmniRoute's default workflow is 512x512, and square has no equivalent on either provider, so
    it lands on landscape rather than being refused."""
    if not width or not height:
        return "16:9"
    return "9:16" if int(height) > int(width) else "16:9"
