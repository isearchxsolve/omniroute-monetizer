"""video_provider_flow.py -- Google Flow (Veo 3.1) as a router provider.

Everything here was lifted out of flow_shim.py unchanged in behaviour. The only additions are the
structured fault codes the self-heal needs, and the last-known-URL bookkeeping that makes recovery
from a closed Chrome possible at all.

WHY A BROWSER MUST STAY RUNNING: the bearer is a web session token read from
labs.google/fx/api/auth/session, and the reCAPTCHA token can only be minted by Google's own JS
inside a real page. Neither has a server-side equivalent. The Chrome window can be minimised and
unfocused and nobody has to click anything -- but it must be alive, and it must be sitting on a
/project/<uuid> URL, because that is the only place the project id exists.

WHAT FLOW CANNOT DO: it cannot be asked a price. There is no quote endpoint, so confirm() can only
report the reservation floor and let Flow's own server-side balance check be the backstop. That is
strictly weaker than rtst's pre-commit refusal, and it is reported as such rather than smoothed over.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import googleflow_client as gf  # noqa: E402
import video_provider as vp  # noqa: E402
from cdp import Page, list_targets  # noqa: E402

FLOW_MATCH = "tools/flow"
FLOW_URL = "https://labs.google/fx/tools/flow"

# MEASURED 2026-08-23 through this shim: one 720p/16:9 8s veo_3_1_t2v_fast clip == 1 media,
# 1 workflow, 950 -> 930 credits. Exactly 20, matching the price shown in the Flow UI.
#
# An earlier 60-credit drop was read as "one clip costs 60 from the API but 20 from the UI"; it was
# not. That drop came from three separate submits run directly through googleflow_client.py during
# capture work, none of which are in the job log. 20 is the price; there is no API penalty.
EST_COST = 20

CHAIN_HELP = {
    "chrome": "Start that account's Chrome with its OWN profile directory and "
              "--remote-debugging-port=<port>. Never the operator's live profile. "
              "`video_router.py wake` does this for you.",
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


class FlowProvider(vp.Provider):
    name = "flow"
    title = "Google Flow (Veo 3.1)"
    tab_match = FLOW_MATCH
    default_url = FLOW_URL
    out_dir = gf.OUT_DIR
    est_cost = EST_COST
    # No per-job ceiling, which is exactly today's behaviour. Flow's clips are a flat 20 and the
    # balance is enforced upstream; adding a ceiling here would change proven behaviour for no gain.
    max_spend_default = None
    quotes_before_spending = False

    # Only the fast key has actually been exercised end to end; the other two follow its naming
    # pattern and are marked so a caller is never told an inference is a measurement.
    proven = {"veo_3_1_t2v_fast"}

    aliases = {
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

    SESSION_TTL = 600          # bearer is good ~12h; re-reading every 10min is cheap insurance

    def owns(self, name: str) -> str | None:
        n = str(name).strip().lower()
        if n.startswith("veo_"):
            return n                       # already a Flow key, pass through untouched
        return super().owns(n)

    # -- request shaping ---------------------------------------------------------------------

    def normalise(self, req: dict) -> tuple[dict | None, str | None]:
        aspect, resolution = req.get("aspect_ratio"), req.get("resolution")
        if req.get("size") and not (aspect and resolution):
            try:
                w, h = (int(x) for x in str(req["size"]).lower().split("x"))
            except Exception:
                return None, "size must look like 1280x720"
            g = self.geometry(w, h)
            aspect, resolution = g["aspect"], g["resolution"]
        aspect = aspect or "16:9"
        resolution = str(resolution or "720p")
        if not resolution.endswith("p") and resolution.isdigit():
            resolution += "p"             # tolerate 720 as well as 720p
        if aspect not in gf.ASPECTS:
            return None, f"aspect_ratio must be one of {list(gf.ASPECTS)}"
        if resolution not in gf.RESOLUTIONS:
            return None, f"resolution must be one of {list(gf.RESOLUTIONS)}"
        return {"model": req["model"], "aspect": aspect, "resolution": resolution,
                "seed": req.get("seed"), "duration": "8s"}, None

    def geometry(self, width: int | None, height: int | None) -> dict:
        """ComfyUI speaks pixels; Flow speaks two enums."""
        res = "720p"
        if width and height and (max(width, height) >= 1920 or min(width, height) >= 1080):
            res = "1080p"
        return {"aspect": vp.pixels_to_aspect(width, height), "resolution": res}

    # -- money -------------------------------------------------------------------------------

    def estimate(self, params: dict) -> int:
        return vp.MEASURED_COST.get(f"{self.name}/{params['model']}", EST_COST)

    def confirm(self, acct: vp.Account, params: dict,
                max_spend: int | None = None) -> tuple[int | None, str | None]:
        """Flow has no quote endpoint, so this cannot refuse on price -- it reports the floor and
        Flow's server-side balance check remains the only real gate. A max_spend can still be
        enforced against the floor (the base class does that), but the caller is told plainly that it
        is an estimate. Deliberately not faked into looking like rtst's pre-commit check."""
        return super().confirm(acct, params, max_spend)

    # -- session, with the one self-heal that matters -----------------------------------------

    def session(self, acct: vp.Account, force: bool = False) -> gf.FlowSession:
        """A live FlowSession for this account, cached briefly.

        The single failure this heals: after the machine sleeps or the tab sits idle for hours,
        /fx/api/auth/session can answer without an access_token until the page is reloaded. That is
        a page-state problem, not a credential problem, so one reload is tried before giving up.
        """
        cached, at = acct.state.get("sess"), acct.state.get("sess_at", 0.0)
        if not force and cached is not None and (time.time() - at) < self.SESSION_TTL:
            return cached

        vp.assert_cdp_safe(f"http://127.0.0.1:{acct.port}", who=f"video_router {acct.label}")
        try:
            sess = gf.FlowSession(FLOW_MATCH, port=acct.port).refresh()
        except vp.NON_FATAL as first:
            if "session token" not in str(first):
                raise
            vp.log(f"{acct.label}: no access_token, reloading the Flow tab once")
            self._reload(acct)
            sess = gf.FlowSession(FLOW_MATCH, port=acct.port).refresh()

        acct.state["sess"], acct.state["sess_at"] = sess, time.time()
        acct.email, acct.project_id, acct.tier = sess.email, sess.project_id, sess.tier
        return sess

    def _reload(self, acct: vp.Account) -> None:
        try:
            with Page(FLOW_MATCH, port=acct.port) as p:
                p.send("Page.reload", {}, timeout=60)
                for _ in range(30):
                    time.sleep(1)
                    try:
                        if p.evaluate("document.readyState", timeout=15) == "complete":
                            break
                    except vp.NON_FATAL:
                        continue
            time.sleep(3)
        except vp.NON_FATAL as e:
            vp.log(f"{acct.label}: reload failed: {type(e).__name__}: {e}")

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

        # The port and the tab are checked separately and BEFORE the session, because those two
        # failures are the heal-able ones and a single "it didn't work" reason cannot tell them
        # apart. Guessing here would mean either never relaunching Chrome, or relaunching it in a
        # loop against a login wall.
        try:
            targets = [t for t in list_targets(acct.port) if t.get("type") == "page"]
        except vp.NON_FATAL as e:
            acct.ready, acct.fault = False, vp.FAULT_PORT
            acct.reason = f"chrome debug port {acct.port} is not answering ({type(e).__name__})"
            return
        tabs = [t for t in targets
                if FLOW_MATCH in (t.get("url", "") + t.get("title", "")).lower()]
        if not tabs:
            acct.ready, acct.fault = False, vp.FAULT_TAB
            acct.reason = f"no Flow tab open on port {acct.port} ({len(targets)} other page(s))"
            return

        try:
            sess = self.session(acct)
            if not sess.project_id:
                acct.ready, acct.fault = False, vp.FAULT_TAB
                acct.reason = "tab is not inside a Flow /project/ URL"
                return
            c = gf.credits_now(sess)
            if c is None:
                acct.ready, acct.fault = False, vp.FAULT_AUTH
                acct.reason = "credits endpoint did not answer 200 (tab is probably signed out)"
                return
            acct.credits, acct.ready, acct.reason = c, True, "ok"
            acct.fault = vp.FAULT_NONE
            # Remember exactly where this worked. Reopening the generic tools/flow URL would lose
            # the project id, so this is the difference between a recoverable account and a manual
            # hunt through the operator's history.
            acct.url = tabs[0].get("url") or acct.url
        except vp.NON_FATAL as e:
            if vp.is_refusal(e):
                acct.enabled = False
                acct.ready, acct.fault = False, vp.FAULT_REFUSED
                acct.reason = "REFUSED: points at the operator's live Chrome"
                vp.log(f"{acct.label}: {acct.reason} -- disabled")
                return
            acct.ready = False
            acct.fault = vp.FAULT_AUTH if "session token" in str(e) else vp.FAULT_OTHER
            acct.reason = f"{type(e).__name__}: {vp.scrub(e)[:160]}"

    # -- the job -----------------------------------------------------------------------------

    def submit(self, acct: vp.Account, params: dict) -> dict:
        sess = self.session(acct)
        before = gf.credits_now(sess)
        r = gf.submit(sess, params["prompt"], model=params["model"],
                      resolution=params["resolution"], aspect=params["aspect"],
                      seed=params.get("seed"))
        media = r.get("media") or []
        # Flow answers one submit with a LIST of medias and bills for every one of them, so every id
        # here is already paid for and every id here gets polled and downloaded. (Measured: a single
        # fast 720p submit returns exactly 1 media for 20 credits. Taking media[0] was still wrong --
        # it silently discards paid output the moment Flow returns more than one.)
        ids = [m.get("name") for m in media
               if isinstance(m, dict) and isinstance(m.get("name"), str) and m.get("name")]
        return {"items": ids, "credits_before": before,
                "credits_after": r.get("remainingCredits"),
                "media_count": len(media), "workflow_count": len(r.get("workflows") or []),
                "project_id": sess.project_id}

    def wait(self, acct: vp.Account, item: str, budget: int, on_status) -> dict:
        # gf.wait calls back with (status, elapsed); the router's interface is a single status line.
        # Absorbed here rather than teaching the router two callback shapes.
        def relay(status, elapsed):
            if on_status:
                on_status(f"{status} @{int(elapsed)}s")

        return gf.wait(self.session(acct), item, budget=int(budget), on_status=relay)

    def duration_of(self, meta: dict) -> str | None:
        try:
            return meta.get("video", {}).get("dimensions", {}).get("length")
        except Exception:
            return None

    def download(self, acct: vp.Account, item: str, meta: dict | None = None) -> pathlib.Path:
        # Must run server-side: the labs.google trpc media redirect is cookie-authenticated and has
        # no CORS, so an in-page fetch cannot follow it.
        return gf.download(item, port=acct.port, verbose=False)

    def recovery_hint(self, item: str) -> str:
        return f"python scripts/automation/googleflow_client.py fetch {item}"

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

        flow = [t for t in targets
                if FLOW_MATCH in (t.get("url", "") + t.get("title", "")).lower()]
        if not flow:
            yield vp.Step("flow tab open", False, "none", CHAIN_HELP["tab"])
            return
        yield vp.Step("flow tab open", True, flow[0].get("url", "")[:60])

        try:
            sess = gf.FlowSession(FLOW_MATCH, port=acct.port).refresh()
        except Exception as e:
            yield vp.Step("session token", False, vp.scrub(e)[:70], CHAIN_HELP["session"])
            return
        yield vp.Step("session token", True, f"{sess.email} expires {sess.expires}")

        if not sess.project_id:
            yield vp.Step("project id", False, "not in a project", CHAIN_HELP["tab"])
            return
        yield vp.Step("project id", True, sess.project_id)

        if not sess.sitekey:
            yield vp.Step("recaptcha sitekey", False, "", CHAIN_HELP["sitekey"])
            return
        yield vp.Step("recaptcha sitekey", True, (sess.sitekey or "")[:24])

        c = gf.credits_now(sess)
        if c is None:
            yield vp.Step("credits rpc", False, "no 200", CHAIN_HELP["credits"])
            return
        yield vp.Step("credits rpc", True, f"{c} credits, tier {sess.tier}")

        try:
            captcha = sess.mint_captcha()
        except Exception as e:
            yield vp.Step("captcha mint", False, vp.scrub(e)[:70], CHAIN_HELP["captcha"])
            return
        yield vp.Step("captcha mint", True, f"{len(captcha)} chars")

        if deep:
            # Zero credits: an EMPTY prompt cannot generate anything, so a complaint about the
            # ARGUMENT is proof the captcha gate was passed.
            body = gf.build_submit_body("", captcha, sess.project_id, tier=sess.tier)
            st, text = gf.request(gf.SUBMIT_URL, sess.token, body)
            kind = gf.classify(text)
            yield vp.Step("captcha accepted", kind == "ARGUMENT",
                          f"HTTP {st} {kind} (0 credits) {vp.scrub(text)[:120]}",
                          CHAIN_HELP["accepted"])


PROVIDER = vp.register(FlowProvider())
