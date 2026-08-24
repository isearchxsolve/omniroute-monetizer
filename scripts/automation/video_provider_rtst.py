"""video_provider_rtst.py -- rtst.ai (Vidu Q2 et al.) as a router provider.

This is a WRAPPER, not a reimplementation. rtst_client.py already holds the parts that were expensive
to learn -- the mandatory "p" suffix on the resolution query param, the terminal-state vocabulary, the
undocumented result-URL field names, and the single in-page fetch that is the only place the bearer is
ever handled. All of it is reused as-is; nothing about the wire contract is restated here.

WHAT rtst BRINGS THAT FLOW CANNOT: an exact price, for free, before committing. GET
/video/estimate-credits answers {credits_required, credits_per_second, current_balance, can_afford,
allowed_durations}, so confirm() is a REAL pre-commit gate -- it re-quotes on the account that was
actually reserved and refuses, at zero cost, if the balance moved or the price exceeds max_spend.
That is why quotes_before_spending is True here and False for Flow.

MEASURED 2026-08-24: vidu, 3s @540p, quoted 6 and charged exactly 6 (30 -> 24), delivered as
state/harvest/rtst/96089.mp4 (872,579 bytes). credits_per_second for vidu is therefore 2.

TRAP, recorded so nobody re-learns it: is_free:true on a model does NOT mean the model is free. wan22
carries that flag and still quotes 10 credits. It means "available on the free plan".
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rtst_client as rt  # noqa: E402
import video_provider as vp  # noqa: E402
from cdp import list_targets  # noqa: E402

# Deliberately low. estimate() only decides WHICH account is big enough; confirm() then re-quotes
# exactly and refuses for free. Under-reserving costs at worst one refused job with nothing spent,
# while over-reserving silently strands accounts that could in fact have paid.
EST_FALLBACK = 2

MIN_PROMPT_WORDS = 10       # MEASURED: 9 words returned VALIDATION_INVALID_PROMPT

CHAIN_HELP = {
    "chrome": "Start the automation Chrome with its OWN profile directory and "
              "--remote-debugging-port=<port>. `video_router.py wake` does this for you.",
    "tab": "In that Chrome, open https://rtst.ai/ and leave it open. Any rtst.ai page will do -- "
           "unlike Flow, no project id is parsed out of the URL.",
    "auth": "The rtst.ai tab has no auth_token in localStorage, i.e. the profile is signed out. "
            "Sign in by hand once; automation never types a password.",
    "models": "GET /videomodel did not answer with a catalogue. Reload the tab and re-check.",
    "quote": "GET /video/estimate-credits refused. Usually a signed-out tab or a model name that "
             "is no longer in the catalogue.",
    "balance": "The balance is too low for the cheapest model on the menu. Top up before submitting.",
}


class RtstProvider(vp.Provider):
    name = "rtst"
    title = "rtst.ai (Vidu Q2 et al.)"
    tab_match = rt.TAB
    default_url = "https://rtst.ai/"
    out_dir = rt.OUT_DIR
    est_cost = EST_FALLBACK
    # Matches rtst_client.py's proven default. Flow's is None because Flow's flat 20 needs no ceiling;
    # rtst prices per second and per model, so a wrong duration is a real overspend risk.
    max_spend_default = 10
    quotes_before_spending = True

    proven = {"vidu"}

    # Seed names, so resolve_model works before anything has been probed. The live catalogue is
    # merged into `catalogue` at probe time and owns() consults it too, so a model rtst adds later is
    # routable without a code change.
    aliases = {
        "vidu": "vidu",
        "vidu-q2": "vidu",
        "viduq2": "vidu",
        "vidu-2": "vidu",
        "wan22": "wan22",
        "wan-2.2": "wan22",
        "wan2.2": "wan22",
    }

    # Shared across rtst accounts on purpose: the model menu is a property of the site, not of a
    # login. Balances stay per-account; only the price list is shared.
    catalogue: dict[str, dict] = {}

    def owns(self, name: str) -> str | None:
        n = str(name).strip().lower()
        got = super().owns(n)
        if got:
            return got
        return n if n in self.catalogue else None

    def model_note(self, key: str) -> str | None:
        if key in self.proven:
            return None
        m = self.catalogue.get(key)
        if m:
            return (f"in the live catalogue at {m.get('credits_per_second', '?')} credits/s but "
                    f"never generated through this router")
        return "model key inferred, never exercised end to end"

    def listing(self) -> list[str]:
        return sorted(set(self.aliases) | set(self.catalogue))

    def describe(self, key: str) -> dict:
        """Adds what the live catalogue knows. The cheapest allowed duration is used for est_cost, to
        match normalise()'s default -- advertising the dearest option as "the" price would be wrong in
        the expensive direction."""
        d = super().describe(key)
        m = self.catalogue.get(key) or {}
        durs, quals = self._allowed(key)
        cps = m.get("credits_per_second")
        try:
            if cps and durs:
                d["est_cost"] = int(cps) * int(durs[0])
        except Exception:
            pass
        d.update(credits_per_second=cps, durations=durs, resolutions=quals,
                 in_live_catalogue=bool(m), min_prompt_words=MIN_PROMPT_WORDS)
        return d

    # -- request shaping ---------------------------------------------------------------------

    def _allowed(self, model: str) -> tuple[list[int], list[int]]:
        m = self.catalogue.get(model) or {}
        durs = sorted({int(d) for d in (m.get("duration") or []) if str(d).isdigit()})
        quals = sorted({int(str(q)) for q in (m.get("video_quality") or []) if str(q).isdigit()})
        return durs, quals

    def normalise(self, req: dict) -> tuple[dict | None, str | None]:
        model = req["model"]
        prompt = str(req.get("prompt") or "")
        # Enforced here rather than discovered at submit time, because rtst validates the prompt
        # BEFORE it checks the balance: a short prompt gets rejected for free, but only after the
        # router has already reserved an account and spun up a worker.
        if len(prompt.split()) < MIN_PROMPT_WORDS:
            return None, (f"rtst.ai requires a prompt of at least {MIN_PROMPT_WORDS} words "
                          f"(got {len(prompt.split())})")

        durs, quals = self._allowed(model)
        # Cheapest allowed is the default, deliberately: an omitted duration must not silently
        # become the most expensive option on the menu.
        duration = req.get("duration")
        resolution = req.get("resolution")
        if duration in (None, ""):
            duration = durs[0] if durs else 3
        if resolution in (None, ""):
            if req.get("size"):
                try:
                    w, h = (int(x) for x in str(req["size"]).lower().split("x"))
                except Exception:
                    return None, "size must look like 1280x720"
                resolution = self.geometry(w, h)["resolution"]
            else:
                resolution = quals[0] if quals else 540
        try:
            duration = int(duration)
            resolution = int(str(resolution).lower().rstrip("p"))
        except Exception:
            return None, "duration must be a whole number of seconds and resolution a number"

        # Only checked when the catalogue is actually known. Guessing a constraint we have not read
        # would refuse valid work; the server validates before charging anyway.
        if durs and duration not in durs:
            return None, f"{model} allows durations {durs} (got {duration})"
        if quals and resolution not in quals:
            return None, f"{model} allows resolutions {quals} (got {resolution})"

        aspect = req.get("aspect_ratio") or "16:9"
        if req.get("size") and not req.get("aspect_ratio"):
            try:
                w, h = (int(x) for x in str(req["size"]).lower().split("x"))
                aspect = vp.pixels_to_aspect(w, h)
            except Exception:
                pass
        return {"model": model, "prompt": prompt, "duration": duration,
                "resolution": resolution, "aspect": aspect,
                "audio": bool(req.get("audio", False))}, None

    def geometry(self, width: int | None, height: int | None) -> dict:
        want = 540
        if width and height:
            small = min(int(width), int(height))
            want = 1080 if small >= 1080 else (720 if small >= 720 else 540)
        return {"aspect": vp.pixels_to_aspect(width, height), "resolution": want}

    # -- money -------------------------------------------------------------------------------

    def estimate(self, params: dict) -> int:
        """Account-independent. rtst prices linearly in seconds (proven: vidu at 2 credits/s, 3s = 6),
        so credits_per_second from the catalogue reproduces the quote without a network call."""
        floor = vp.MEASURED_COST.get(f"{self.name}/{params['model']}")
        m = self.catalogue.get(params["model"]) or {}
        cps = m.get("credits_per_second")
        try:
            est = int(cps) * int(params["duration"]) if cps else 0
        except Exception:
            est = 0
        return max(est, floor or 0) or EST_FALLBACK

    def _raw_quote(self, acct: vp.Account, params: dict) -> dict:
        """GET /video/estimate-credits, verbatim. Free, read-only, and the one place the price comes
        from -- both quote() and confirm() go through here so they can never disagree."""
        with rt.Rtst(acct.port) as c:
            q = c.quote(model=params["model"], duration=params["duration"],
                        resolution=params["resolution"], aspect=params.get("aspect") or "16:9",
                        audio=bool(params.get("audio")))
        bal = q.get("current_balance")
        if isinstance(bal, int):
            acct.credits = bal              # authoritative and free; the cached figure is a snapshot
        return q

    def quote(self, acct: vp.Account, params: dict) -> tuple[int | None, str | None]:
        """The exact price with no ceiling applied. Affordability is reported, not enforced: this is
        the operator asking what something costs, and refusing to answer would be unhelpful."""
        try:
            q = self._raw_quote(acct, params)
        except vp.NON_FATAL as e:
            return None, f"quote failed: {vp.scrub(e)[:200]}"
        need = int(q.get("credits_required") or 0)
        if not q.get("can_afford"):
            return need, (f"quoted {need} credits but the balance is "
                          f"{q.get('current_balance')} -- not affordable")
        return need, None

    def confirm(self, acct: vp.Account, params: dict,
                max_spend: int | None = None) -> tuple[int | None, str | None]:
        """The real pre-commit gate, run on the account that was actually reserved.

        Three refusals, all free: the quote endpoint itself failing, can_afford being false (the
        balance moved between probe and now), and the exact price exceeding the ceiling. This is the
        same gate rtst_client.py's `submit` enforces, kept in place rather than dropped because the
        caller is now a server instead of a human at a prompt.
        """
        ceiling = self.max_spend_default if max_spend is None else max_spend
        try:
            q = self._raw_quote(acct, params)
        except vp.NON_FATAL as e:
            return None, f"quote failed, refusing to spend blind: {vp.scrub(e)[:200]}"
        need = int(q.get("credits_required") or 0)
        bal = q.get("current_balance")
        if not q.get("can_afford"):
            return None, f"rtst refuses: {need} credits required, balance {bal}"
        if ceiling is not None and need > int(ceiling):
            return None, f"quote {need} credits exceeds max_spend {ceiling}"
        if need <= 0:
            return None, f"quote returned a non-positive price ({need}); refusing to submit blind"
        return need, None

    # -- probe -------------------------------------------------------------------------------

    def probe(self, acct: vp.Account) -> None:
        try:
            vp.assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who=f"video_router {acct.label}")
        except Exception as e:
            if vp.is_refusal(e):
                acct.enabled = False
                acct.ready, acct.fault = False, vp.FAULT_REFUSED
                acct.reason = "REFUSED: points at the operator's live Chrome"
                vp.log(f"{acct.label}: {acct.reason} -- disabled")
                return
            acct.ready, acct.fault = False, vp.FAULT_OTHER
            acct.reason = f"{type(e).__name__}: {vp.scrub(e)[:160]}"
            return

        try:
            targets = [t for t in list_targets(acct.port) if t.get("type") == "page"]
        except vp.NON_FATAL as e:
            acct.ready, acct.fault = False, vp.FAULT_PORT
            acct.reason = f"chrome debug port {acct.port} is not answering ({type(e).__name__})"
            return
        tabs = [t for t in targets
                if rt.TAB in (t.get("url", "") + t.get("title", "")).lower()]
        if not tabs:
            acct.ready, acct.fault = False, vp.FAULT_TAB
            acct.reason = f"no rtst.ai tab open on port {acct.port} ({len(targets)} other page(s))"
            return

        try:
            with rt.Rtst(acct.port) as c:
                acct.credits = c.credits()
                try:
                    cat = {m["name"]: m for m in c.models() if isinstance(m.get("name"), str)}
                except vp.NON_FATAL as e:
                    # A missing catalogue is not a dead account: the seed aliases still route and the
                    # server still validates. Degrade, note it, stay ready.
                    cat = {}
                    vp.log(f"{acct.label}: model catalogue unavailable ({vp.scrub(e)[:80]})")
            if cat:
                type(self).catalogue = cat
                acct.state["models"] = cat
            acct.ready, acct.reason, acct.fault = True, "ok", vp.FAULT_NONE
            acct.url = tabs[0].get("url") or acct.url
        except vp.NON_FATAL as e:
            if vp.is_refusal(e):
                acct.enabled = False
                acct.ready, acct.fault = False, vp.FAULT_REFUSED
                acct.reason = "REFUSED: points at the operator's live Chrome"
                vp.log(f"{acct.label}: {acct.reason} -- disabled")
                return
            msg = str(e)
            acct.ready = False
            acct.fault = (vp.FAULT_AUTH if ("auth_token" in msg or "signed out" in msg)
                          else vp.FAULT_OTHER)
            acct.reason = f"{type(e).__name__}: {vp.scrub(e)[:160]}"

    # -- the job -----------------------------------------------------------------------------

    def submit(self, acct: vp.Account, params: dict) -> dict:
        """One submit, one video id, no retry.

        rtst's create response carries no balance, so the balance is re-read immediately afterwards.
        That read is free and read-only, and it is what lets the router's
        stale-balance-after-a-charged-submit guard work for this provider unchanged.
        """
        with rt.Rtst(acct.port) as c:
            before = c.credits()
            got = c.submit(prompt=params["prompt"], model=params["model"],
                           duration=params["duration"], resolution=params["resolution"],
                           aspect=params["aspect"], audio=params["audio"])
            vid = str(got.get("id") or got.get("video_id") or got.get("uuid") or "").strip()
            try:
                after = c.credits()
            except vp.NON_FATAL as e:
                after = None
                vp.log(f"{acct.label}: balance re-read failed after a charged submit: "
                       f"{vp.scrub(e)[:120]}")
        if not vid:
            # Money may well have moved and there is nothing to poll. Loud, with the raw response, so
            # the id can be recovered by hand from rtst.ai's own history page.
            vp.log(f"!! {acct.label}: submit returned no video id; balance {before} -> {after}. "
                   f"Raw: {vp.scrub(json.dumps(got))[:400]}")
        return {"items": [vid] if vid else [], "credits_before": before, "credits_after": after,
                "media_count": 1 if vid else 0, "workflow_count": 1 if vid else 0,
                "quoted": params.get("quoted")}

    def wait(self, acct: vp.Account, item: str, budget: int, on_status) -> dict:
        """Poll to a terminal state.

        rt.wait_loop is not called directly for one reason only: it prints its own progress and takes
        no callback, and the router needs the status stream for /queue and the job record. Everything
        that was actually hard -- the terminal-state vocabulary and the result-URL field hunt -- is
        still rt.DONE / rt.FAILED / rt.pick_url, single-sourced.
        """
        deadline, last = time.time() + int(budget), None
        with rt.Rtst(acct.port) as c:
            while time.time() < deadline:
                d = c.status(item)
                st = str(d.get("status") or d.get("state") or "").lower()
                if st != last and on_status:
                    on_status(st or "(no status field)")
                last = st
                if st in rt.DONE or rt.pick_url(d):
                    return d
                if st in rt.FAILED:
                    raise RuntimeError(f"generation failed: {vp.scrub(json.dumps(d))[:300]}")
                time.sleep(6)
        raise RuntimeError(f"still not finished after {budget}s; the credits are already spent -- "
                           f"{self.recovery_hint(item)}")

    def duration_of(self, meta: dict) -> str | None:
        for k in ("duration", "length", "video_duration"):
            v = meta.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return f"{v}s"
            if isinstance(v, str) and v.strip():
                return v if v.strip().endswith("s") else f"{v}s"
        return None

    def download(self, acct: vp.Account, item: str, meta: dict | None = None) -> pathlib.Path:
        url = rt.pick_url(meta) if isinstance(meta, dict) else None
        if not url:
            with rt.Rtst(acct.port) as c:
                url = rt.pick_url(c.status(item))
        if not url:
            raise RuntimeError(f"no downloadable url for {item}; {self.recovery_hint(item)}")
        # Plain urllib, no browser: the finished asset sits on a public CDN URL with no auth, which is
        # how rtst_client.py's own download works. Nothing here needs the bearer.
        self.out_dir.mkdir(parents=True, exist_ok=True)
        dest = self.out_dir / f"{item}.mp4"
        with urllib.request.urlopen(url, timeout=300) as r, dest.open("wb") as fh:
            fh.write(r.read())
        return dest

    def recovery_hint(self, item: str) -> str:
        return f"python scripts/automation/rtst_client.py download {item}"

    # -- operator help -----------------------------------------------------------------------

    def doctor_chain(self, acct: vp.Account, deep: bool = False):
        try:
            vp.assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who="video_router doctor")
        except Exception as e:
            if vp.is_refusal(e):
                yield vp.Step("live-profile guard", False,
                              "REFUSED -- this port is the operator's Chrome", CHAIN_HELP["chrome"])
                return
            raise
        yield vp.Step("live-profile guard", True, "not the operator's profile")

        try:
            targets = [t for t in list_targets(acct.port) if t.get("type") == "page"]
        except Exception as e:
            yield vp.Step("chrome debug port", False, f"{type(e).__name__}: {str(e)[:60]}",
                          CHAIN_HELP["chrome"])
            return
        yield vp.Step("chrome debug port", True, f"{len(targets)} page target(s)")

        tabs = [t for t in targets if rt.TAB in (t.get("url", "") + t.get("title", "")).lower()]
        if not tabs:
            yield vp.Step("rtst tab open", False, "none", CHAIN_HELP["tab"])
            return
        yield vp.Step("rtst tab open", True, tabs[0].get("url", "")[:60])

        try:
            with rt.Rtst(acct.port) as c:
                bal = c.credits()
                try:
                    models = c.models()
                except Exception as e:
                    yield vp.Step("auth token + balance", True,
                                  f"{bal} credits (bearer used inside the page only)")
                    yield vp.Step("model catalogue", False, vp.scrub(e)[:70], CHAIN_HELP["models"])
                    return
                yield vp.Step("auth token + balance", True,
                              f"{bal} credits (bearer used inside the page only)")
                yield vp.Step("model catalogue", True, f"{len(models)} model(s): " +
                              ", ".join(str(m.get("name")) for m in models[:6]))

                # A free exact quote is the whole reason this provider was chosen; it is a rung, not
                # an extra. Cheapest model first, so this doubles as an affordability check.
                cheapest, dearest = None, None
                for m in models:
                    durs = sorted(int(d) for d in (m.get("duration") or []) if str(d).isdigit())
                    quals = sorted(int(str(q)) for q in (m.get("video_quality") or [])
                                   if str(q).isdigit())
                    if not durs or not quals:
                        continue
                    try:
                        q = c.quote(model=m["name"], duration=durs[0], resolution=quals[0])
                    except Exception:
                        continue
                    need = int(q.get("credits_required") or 0)
                    tag = (m["name"], need, durs[0], quals[0], bool(q.get("can_afford")))
                    if q.get("can_afford") and (cheapest is None or need < cheapest[1]):
                        cheapest = tag
                    est = max(durs) * (m.get("credits_per_second") or 0)
                    if dearest is None or est > dearest[1]:
                        dearest = (m["name"], est, max(durs), quals[-1])
                if cheapest is None:
                    yield vp.Step("free exact quote", False,
                                  "nothing on the menu is affordable at this balance",
                                  CHAIN_HELP["balance"])
                    return
                yield vp.Step("free exact quote", True,
                              f"{cheapest[0]} {cheapest[2]}s @{cheapest[3]}p = {cheapest[1]} "
                              f"credits ({bal // cheapest[1]} run(s) available), 0 spent")

                if deep:
                    # rtst_client.cmd_contract's technique: a WELL-FORMED request for something
                    # demonstrably unaffordable must be rejected, so no video can be created, yet the
                    # rejection proves the create endpoint accepts our payload shape. Skipped rather
                    # than risked if the expensive option turns out to be affordable.
                    if dearest is None:
                        yield vp.Step("create-endpoint contract", False,
                                      "no model has usable duration/quality metadata",
                                      CHAIN_HELP["models"])
                        return
                    q = c.quote(model=dearest[0], duration=dearest[2], resolution=dearest[3],
                                audio=True)
                    if q.get("can_afford"):
                        yield vp.Step("create-endpoint contract", True,
                                      f"SKIPPED on purpose: {dearest[0]} at "
                                      f"{q.get('credits_required')} credits IS affordable, so a "
                                      f"probe could actually succeed and charge")
                        return
                    try:
                        got = c.submit(prompt="a contract probe request that must be rejected for "
                                              "having insufficient credits on this account",
                                       model=dearest[0], duration=dearest[2],
                                       resolution=dearest[3], audio=True)
                        yield vp.Step("create-endpoint contract", False,
                                      "!! the server ACCEPTED an unaffordable request: "
                                      + vp.scrub(json.dumps(got))[:200],
                                      "check the balance immediately -- this may have charged")
                    except Exception as e:
                        yield vp.Step("create-endpoint contract", True,
                                      f"rejected as expected, 0 credits: {vp.scrub(e)[:120]}")
        except Exception as e:
            msg = str(e)
            yield vp.Step("auth token + balance", False, vp.scrub(e)[:70],
                          CHAIN_HELP["auth"] if ("auth_token" in msg or "signed out" in msg)
                          else CHAIN_HELP["quote"])


PROVIDER = vp.register(RtstProvider())
