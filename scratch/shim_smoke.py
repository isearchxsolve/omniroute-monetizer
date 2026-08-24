"""Dry-run smoke test for video_router: proves the money bugs are actually closed without spending
a credit. Exercises the exact JSON OmniRoute's compiled comfyui handler emits.

All 22 checks written against the Flow-only shim are kept verbatim in intent -- they are the
regression net for the money review in worklog #1063/#1064, and a refactor that quietly dropped one
would be indistinguishable from a refactor that broke it. The new checks below them cover the
two-provider seam: routing, per-provider isolation of both the account pool and the cost floor,
rtst's pre-commit refusals, the 5-character media id, the self-heal guards and the registry
migration. Still 0 credits: nothing here submits, and the only network is loopback."""
import json, pathlib, socket, subprocess, sys, time, urllib.error, urllib.request

D, C = "http://127.0.0.1:8189", "http://127.0.0.1:8188"

# Snapshotted BEFORE the server starts. This suite runs a --dry-run serve and then queues jobs
# through both faces, so if a rehearsal record can reach the money ledger, it reaches it here.
LEDGER = pathlib.Path("D:/omniroute-monetizer/state/video_jobs.jsonl")
DRY_LEDGER = LEDGER.with_name("video_jobs.dryrun.jsonl")
LEDGER_BEFORE = LEDGER.read_bytes() if LEDGER.exists() else b""
DRY_BEFORE = DRY_LEDGER.stat().st_size if DRY_LEDGER.exists() else 0


def call(url, payload=None, token=None):
    req = urllib.request.Request(url, method="POST" if payload is not None else "GET",
                                data=json.dumps(payload).encode() if payload is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))


def wf(pos, neg, w=1280, h=720):
    """OmniRoute's generated workflow shape: two CLIPTextEncode nodes, told apart only by which
    KSampler input links to them."""
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animatediff"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": 4242424242, "steps": 20,
                                                   "model": ["1", 0], "positive": ["2", 0],
                                                   "negative": ["3", 0], "latent_image": ["4", 0]}},
        "7": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["6", 0]}},
    }}


srv = subprocess.Popen([sys.executable, "-u", "scripts/automation/video_router.py", "serve",
                        "--dry-run", "--token", "smoketoken"],
                       cwd="D:/omniroute-monetizer", stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
fails = []
try:
    for _ in range(40):
        time.sleep(0.5)
        try:
            call(D + "/healthz")
            break
        except Exception:
            continue

    def check(name, cond, detail=""):
        print(f"  [{'ok  ' if cond else 'FAIL'}] {name}  {detail}")
        if not cond:
            fails.append(name)

    print("\n-- secrets: pre-auth /healthz must not name an account -------------------")
    st, h = call(D + "/healthz")
    keys = set(h["accounts"][0]) if h.get("accounts") else set()
    check("redacted without a token", not ({"email", "credits", "reason", "tier"} & keys),
          f"keys={sorted(keys)}")
    check("measured_cost withheld", h.get("measured_cost") is None)
    # url is the one field the two-provider registry added to the redacted shape's blast radius: it
    # is the remembered tab URL, and for Flow that URL contains /project/<uuid>.
    check("remembered tab url withheld", "url" not in keys, f"keys={sorted(keys)}")
    check("heal counters withheld", h.get("heal") is None)
    # Which paid vendors this machine holds credentials for is not a liveness fact. Withholding the
    # per-account `provider` only works if the global list goes too -- with two adapters registered,
    # the list plus a port is enough to infer the pairing.
    check("per-account provider withheld", "provider" not in keys, f"keys={sorted(keys)}")
    check("global provider list withheld", h.get("providers") is None, str(h.get("providers")))
    st, h2 = call(D + "/healthz", token="smoketoken")
    check("full shape with a token", "credits" in (h2["accounts"][0] if h2.get("accounts") else {}))
    check("provider named once authenticated",
          "provider" in (h2["accounts"][0] if h2.get("accounts") else {})
          and isinstance(h2.get("providers"), list), str(h2.get("providers")))
    st, _ = call(D + "/v1/accounts")
    check("/v1/accounts still 401s", st == 401, f"HTTP {st}")

    print("\n-- money: the reservation floor must never ratchet upward ----------------")
    # A dry run charges nothing, so this path is unreachable through HTTP. Test it directly.
    # The hazard: credits_before is read from the account and credits_after comes from the submit
    # response, so any concurrent spend on that account lands inside the window and inflates the
    # delta. If that inflated delta became the floor, acquire() would refuse every account holding
    # less than it -- capacity stranded for good.
    sys.path.insert(0, "scripts/automation")
    import video_router as vr
    vp = vr.vp                      # the floor and the provider registry live in video_provider now
    M = "flow/veo_3_1_t2v_fast"     # ... and the floor is keyed "<provider>/<model>"
    vp.MEASURED_COST.clear()
    vp.observe_cost(M, 20, 1)
    check("an honest run sets the floor", vp.MEASURED_COST.get(M) == 20, f"floor={vp.MEASURED_COST.get(M)}")
    vp.observe_cost(M, 80, 1)
    check("a concurrent external spend cannot raise it", vp.MEASURED_COST.get(M) == 20,
          f"floor={vp.MEASURED_COST.get(M)}")
    vp.observe_cost(M, 40, 4)
    check("multi-media cost is divided per media", vp.MEASURED_COST.get(M) == 10,
          f"floor={vp.MEASURED_COST.get(M)}")
    for label, charged, n in (("absurd delta ignored", 5000, 1), ("negative delta ignored", -30, 1),
                              ("missing billing data ignored", None, None)):
        vp.observe_cost(M, charged, n)
        check(label, vp.MEASURED_COST.get(M) == 10, f"floor={vp.MEASURED_COST.get(M)}")

    print("\n-- contract: negative prompt must never be rendered as the positive ------")
    st, r = call(C + "/prompt", wf("", "blurry, low quality, distorted"))
    check("blank positive is refused", st == 400, f"HTTP {st} {str(r)[:90]}")
    st, r = call(C + "/prompt", wf("a lighthouse in a storm", "blurry, low quality"))
    check("normal workflow accepted", st == 200 and "prompt_id" in r, f"HTTP {st}")
    jid = r.get("prompt_id")
    # Positive/negative are swapped in the links: the shim must follow the link, not the order.
    swapped = wf("blurry, low quality", "a lighthouse in a storm")
    swapped["prompt"]["5"]["inputs"]["positive"] = ["3", 0]
    swapped["prompt"]["5"]["inputs"]["negative"] = ["2", 0]
    st2, r2 = call(C + "/prompt", swapped)
    check("link order beats node order", st2 == 200, f"HTTP {st2}")

    print("\n-- http: malformed input must 400, never crash the connection ------------")
    for label, payload in (("non-object body", [1, 2, 3]), ("prompt not a dict", {"prompt": "x"})):
        st, r = call(C + "/prompt", payload)
        check(label + " -> 400", st == 400, f"HTTP {st}")
    st, r = call(D + "/v1/videos/generations",
                 {"prompt": "x", "model": "fast", "wait_timeout": "not-a-number"},
                 token="smoketoken")
    check("bad wait_timeout rejected before any job", st == 400, f"HTTP {st} {str(r)[:70]}")
    st, r = call(D + "/v1/videos/generations", {"prompt": "x", "model": "fast", "seed": 10 ** 12},
                 token="smoketoken")
    check("out-of-range seed rejected", st == 400, f"HTTP {st}")

    print("\n-- comfyui: /queue must not hand out job ids -----------------------------")
    st, q = call(C + "/queue")
    check("no ids in /queue", q.get("queue_running") == [] and q.get("queue_pending") == [],
          str(q.get("video_router")))

    print("\n-- end to end through the ComfyUI contract -------------------------------")
    outs = None
    for _ in range(30):
        time.sleep(1)
        st, hist = call(C + f"/history/{jid}")
        if hist.get(jid, {}).get("outputs"):
            outs = hist[jid]["outputs"]
            break
    check("outputs appeared", bool(outs), str(outs)[:110])
    if outs:
        gifs = list(outs.values())[0]["gifs"]
        check("one entry per paid media", len(gifs) >= 1, f"{len(gifs)} file(s)")
        fn = gifs[0]["filename"]
        req = urllib.request.Request(C + "/view?filename=" + fn + "&subfolder=&type=output")
        with urllib.request.urlopen(req, timeout=60) as rr:
            body = rr.read()
        check("bytes served and look like MP4", len(body) > 10000 and b"ftyp" in body[:64],
              f"{len(body)} bytes")
    st, j = call(D + f"/v1/videos/generations/{jid}", token="smoketoken")
    check("direct face agrees", j.get("status") == "succeeded",
          f"{j.get('status')} media_ids={j.get('media_ids')} content_urls={j.get('content_urls')}")

    # ====================================================================================
    # the two-provider seam. everything below is in-process and offline: no browser, no
    # submit, no network beyond the loopback server already running.
    # ====================================================================================

    print("\n-- routing: a name must land on exactly one provider ----------------------")
    p, k, e = vp.resolve_model("veo-3.1-fast")
    check("veo-3.1-fast -> flow", p is not None and p.name == "flow" and k == "veo_3_1_t2v_fast",
          f"{p and p.name}/{k} {e or ''}")
    p, k, e = vp.resolve_model("vidu")
    check("vidu -> rtst", p is not None and p.name == "rtst" and k == "vidu",
          f"{p and p.name}/{k} {e or ''}")
    p, k, e = vp.resolve_model("comfyui/veo-3.1-fast")
    check("OmniRoute's prefixed name still resolves", p is not None and p.name == "flow", f"{e or ''}")
    p, k, e = vp.resolve_model("rtst/veo-3.1-fast")
    check("a pinned prefix cannot cross providers", p is None and e is not None, f"{e or ''}")
    p, k, e = vp.resolve_model("definitely-not-a-real-model")
    check("unknown name refused, naming both providers",
          p is None and e is not None and "flow/" in e and "rtst/" in e, (e or "")[:70])

    print("\n-- isolation: one provider's job must never touch another's account -------")
    flow_only = vr.Fleet([vp.Account("flow", 9222, "flow-x")])
    flow_only.accounts[0].ready, flow_only.accounts[0].credits = True, 950
    try:
        got = flow_only.acquire("rtst", 2, timeout=0.1)
        got.lock.release()
        check("acquire('rtst') with only a flow account raises", False, f"handed out {got.label}")
        check("the flow account was not handed out", False)
    except Exception as exc:
        check("acquire('rtst') with only a flow account raises", "rtst" in str(exc),
              f"{type(exc).__name__}: {str(exc)[:80]}")
        check("the flow account was not handed out", not flow_only.accounts[0].lock.locked())
    check("...and the same fleet still serves flow",
          flow_only.acquire("flow", 20, timeout=0.1).label == "flow-x")
    flow_only.accounts[0].lock.release()

    two = vr.Fleet([vp.Account("flow", 9222, "f1"), vp.Account("rtst", 9222, "r1")])
    for x in two.accounts:
        x.ready, x.credits = True, 100
    f1 = two.acquire("flow", 20, timeout=0.1)
    # Same Chrome, same port, two tabs, two balances -- a per-port lock would serialise two jobs that
    # physically cannot collide.
    check("two accounts on one port have independent locks",
          two.accounts[0].lock is not two.accounts[1].lock and not two.accounts[1].lock.locked())
    r1 = two.acquire("rtst", 2, timeout=0.1)
    check("rtst is acquirable while flow is busy on the same port", r1.label == "r1")
    f1.lock.release()
    r1.lock.release()

    print("\n-- money: the floor is per provider, and rtst refuses before spending -----")
    vp.MEASURED_COST.clear()
    vp.observe_cost("flow/veo_3_1_t2v_fast", 20, 1)
    vp.observe_cost("rtst/vidu", 6, 1)
    vp.observe_cost("flow/veo_3_1_t2v_fast", 10, 1)
    check("moving flow's floor leaves rtst's alone",
          vp.MEASURED_COST.get("flow/veo_3_1_t2v_fast") == 10
          and vp.MEASURED_COST.get("rtst/vidu") == 6, str(dict(vp.MEASURED_COST)))
    vp.MEASURED_COST.clear()

    rtst = vp.get("rtst")
    acct = vp.Account("rtst", 9222, "r-stub")
    acct.ready, acct.credits = True, 24
    params = {"model": "vidu", "duration": 3, "resolution": 540, "aspect": "16:9", "audio": False}
    real_raw = rtst._raw_quote
    try:
        # A stub, because the point is the GATE, not the endpoint: confirm() must refuse on each of
        # these without a submit, and it must do so for free.
        rtst._raw_quote = lambda a, p: {"credits_required": 6, "current_balance": 2,
                                        "can_afford": False}
        cost, err = rtst.confirm(acct, params)
        check("confirm refuses on can_afford: false", cost is None and err and "refuses" in err,
              (err or "")[:70])
        rtst._raw_quote = lambda a, p: {"credits_required": 24, "current_balance": 500,
                                        "can_afford": True}
        cost, err = rtst.confirm(acct, params, max_spend=10)
        check("confirm refuses above max_spend", cost is None and err and "max_spend" in err,
              (err or "")[:70])
        cost, err = rtst.confirm(acct, params, max_spend=30)
        check("confirm allows an affordable quote under the ceiling", cost == 24 and not err,
              f"{cost} {err or ''}")
        rtst._raw_quote = lambda a, p: {"credits_required": 0, "current_balance": 500,
                                        "can_afford": True}
        cost, err = rtst.confirm(acct, params)
        check("confirm refuses a non-positive price", cost is None and err, (err or "")[:70])

        def boom(a, p):
            raise RuntimeError("estimate-credits 500")
        rtst._raw_quote = boom
        cost, err = rtst.confirm(acct, params)
        check("a failed quote refuses rather than spending blind",
              cost is None and err and "blind" in err, (err or "")[:70])
    finally:
        rtst._raw_quote = real_raw

    print("\n-- money: rtst's offline estimate must match its own quote ----------------")
    # MEASURED 2026-08-24 over 87 free estimate-credits reads: credits_required is exactly
    # credits_per_second * duration, where that rate depends on the QUALITY and on AUDIO. The
    # catalogue's single per-model figure is not that rate, so `cps * duration` over-reserved 3x at
    # vidu 540p and under-reserved at 1080p. estimate() only picks WHICH account to reserve, so a
    # wrong number here strands capacity or fails a job that could have run -- it cannot lose money,
    # because confirm() still re-quotes exactly.
    vpr = sys.modules["video_provider_rtst"]
    for res, audio, want in ((540, False, 6), (720, False, 18), (1080, False, 27),
                             (540, True, 15), (720, True, 27), (1080, True, 36)):
        got = rtst.estimate({"model": "vidu", "duration": 3, "resolution": res, "audio": audio})
        check(f"vidu 3s @{res}p {'audio' if audio else 'mute '} estimates {want}", got == want,
              f"got {got}")
    check("wan22 5s @480p estimates the measured 10, not cps*duration=25",
          rtst.estimate({"model": "wan22", "duration": 5, "resolution": 480}) == 10,
          str(rtst.estimate({"model": "wan22", "duration": 5, "resolution": 480})))
    check("'540', '540p' and 540 are one rate key",
          len({vpr.rate_key("vidu", "540", False), vpr.rate_key("vidu", "540p", False),
               vpr.rate_key("vidu", 540, False)}) == 1)
    # The floor is a flat per-media charge; an rtst price is a function of duration and quality. Fold
    # one into the other with max() and a single 90-credit 10s/1080p job makes every 6-credit
    # 3s/540p request reserve 90 -- 15x the capacity it needs, stranded.
    vp.MEASURED_COST["rtst/vidu"] = 90
    try:
        check("a big past charge cannot inflate a cheap estimate",
              rtst.estimate({"model": "vidu", "duration": 3, "resolution": 540}) == 6,
              str(rtst.estimate({"model": "vidu", "duration": 3, "resolution": 540})))
    finally:
        vp.MEASURED_COST.clear()

    saved_rate = dict(vpr.RATE)
    try:
        # A quote reply carries the resolved rate for free, so every quote teaches the next estimate.
        vpr.RATE.pop("vidu/720/mute", None)
        rtst._learn_rate({"model": "vidu", "duration": 3, "resolution": "720", "audio": False},
                         {"credits_required": 18, "credits_per_second": 6, "duration": 3,
                          "resolution": "720p"})
        check("a live quote teaches the rate table", vpr.RATE.get("vidu/720/mute") == 6,
              str(vpr.RATE.get("vidu/720/mute")))
        rtst._learn_rate({"model": "vidu", "duration": 3, "resolution": "720", "audio": False},
                         {"credits_required": 25, "credits_per_second": 6, "duration": 3,
                          "resolution": "720p"})
        check("a reply that breaks rate*duration is NOT learned from",
              vpr.RATE.get("vidu/720/mute") == 6, str(vpr.RATE.get("vidu/720/mute")))
        rtst._learn_rate({"model": "vidu", "duration": 3, "resolution": "720", "audio": False},
                         {"credits_required": 21, "credits_per_second": 7, "duration": 3,
                          "resolution": "720p"})
        check("a genuine re-price is picked up", vpr.RATE.get("vidu/720/mute") == 7,
              str(vpr.RATE.get("vidu/720/mute")))
    finally:
        vpr.RATE.clear()
        vpr.RATE.update(saved_rate)
    saved_cat = type(rtst).catalogue
    try:
        # describe() needs a catalogue to know the cheapest allowed duration and quality; this process
        # never probed, so stand in the measured one rather than skip the check.
        type(rtst).catalogue = {"vidu": {"credits_per_second": 6, "duration": [3, 10],
                                        "video_quality": [540, 720, 1080]}}
        d = rtst.describe("vidu")
        check("/v1/models advertises the same price the router reserves",
              d.get("est_cost") == rtst.estimate({"model": "vidu", "duration": 3,
                                                  "resolution": 540}) == 6,
              f"est_cost={d.get('est_cost')}")
        check("...and publishes the per-quality rates the catalogue lacks",
              (d.get("credits_per_second_by_quality") or {}).get("540p") == 2,
              str(d.get("credits_per_second_by_quality")))
    finally:
        type(rtst).catalogue = saved_cat

    print("\n-- validation happens before a thread or an account is reserved -----------")
    bad, err = rtst.normalise({"model": "vidu", "prompt": "nine words is not quite enough here ok",
                              "duration": 3, "resolution": 540})
    check("a <10-word rtst prompt is refused at normalise", bad is None and err and "10 words" in err,
          (err or "")[:70])
    ok, err = rtst.normalise({"model": "vidu", "duration": 3, "resolution": 540,
                              "prompt": "a lighthouse in a violent storm at night with waves "
                                        "crashing over the rocks below it"})
    check("a long enough prompt normalises", ok is not None and not err, str(ok)[:80])
    st, r = call(D + "/v1/videos/generations",
                 {"prompt": "too short", "model": "vidu"}, token="smoketoken")
    check("...and the direct face returns it as a 400, no job created", st == 400,
          f"HTTP {st} {str(r)[:80]}")

    print("\n-- media ids: 5 characters is legal, traversal is not ---------------------")
    resolve = vr.Base._resolve_media_file
    rtst_clip = next((d / "96089.mp4" for d in vp.out_dirs() if (d / "96089.mp4").exists()), None)
    check("the proven rtst clip is on disk to test against", rtst_clip is not None,
          str(rtst_clip or [str(d) for d in vp.out_dirs()]))
    if rtst_clip:
        # The old regex floor was {6,80}. Every rtst id is 5 characters, so that floor 404'd the
        # entire provider; the charset plus the containment check is what actually guards this.
        check("a 5-character rtst id resolves", resolve(None, "96089") == rtst_clip.resolve(),
              str(resolve(None, "96089")))
        check("...and so does it with .mp4 on the end", resolve(None, "96089.mp4") is not None)
    for hostile in ("../../../../Windows/System32/drivers/etc/hosts", "..\\..\\secrets",
                    "state/flow_accounts.json", "/etc/passwd", "96089/../../x", "", "a b", "a;b"):
        check(f"refused: {hostile[:34]!r}", resolve(None, hostile) is None)
    check("an id outside every out dir is refused", resolve(None, "aaaaaaaaaaaa") is None)
    check("containment covers both out dirs", len(vp.out_dirs()) >= 2,
          str([d.name for d in vp.out_dirs()]))

    print("\n-- self-heal: bounded, and never against a login wall --------------------")
    heal_fleet = vr.Fleet([vp.Account("flow", 39999, "h1")])
    a1 = heal_fleet.accounts[0]
    a1.ready, a1.fault, a1.reason = False, vp.FAULT_AUTH, "credits endpoint did not answer 200"
    rec = heal_fleet._heal_one(a1)
    check("a signed-out account is never heal-able",
          rec and rec["action"] == "skip" and not rec["ok"] and "password" in rec["detail"],
          str(rec and rec["detail"])[:70])
    check("...and it is counted as such", heal_fleet.heal_stats["not_healable"] == 1)
    check("FAULT_AUTH is not in HEALABLE", vp.FAULT_AUTH not in vp.HEALABLE, str(vp.HEALABLE))
    allowed, wait = heal_fleet._may_attempt(39999)
    check("the first launch on a port is allowed", allowed and wait == 0)
    heal_fleet._arm_backoff(39999, ok=False)
    allowed, wait = heal_fleet._may_attempt(39999)
    check("a second launch inside the window is refused", not allowed and wait > 0, f"{wait:.0f}s")
    heal_fleet._arm_backoff(39999, ok=False)
    allowed2, wait2 = heal_fleet._may_attempt(39999)
    check("consecutive failures double the wait",
          not allowed2 and wait2 >= vr.HEAL_BACKOFF_MIN * 2 - 5,
          f"{wait2:.0f}s after 2 failures (min {vr.HEAL_BACKOFF_MIN}, cap {vr.HEAL_BACKOFF_MAX})")
    a1.ready, a1.fault = False, vp.FAULT_PORT
    a1.lock.acquire()
    rec = heal_fleet._heal_one(a1)
    check("a busy account is never healed under a running job",
          rec and rec["action"] == "skip" and "busy" in rec["detail"], str(rec and rec["detail"])[:60])
    a1.lock.release()
    refused = vp.Account("flow", 9222, "r-refused")
    refused.ready, refused.fault, refused.enabled = False, vp.FAULT_REFUSED, False
    check("a REFUSED account is left alone entirely",
          vr.Fleet([refused])._heal_one(refused) is None)

    print("\n-- self-heal: a discarded tab is its own fault, and heal-able -------------")
    # MEASURED 2026-08-24: Chrome's memory saver discarded both automation tabs. The port answered,
    # /json/list still listed the tabs, browser-domain CDP answered instantly -- only Runtime.evaluate
    # hung. Classified FAULT_OTHER that is "reported, never acted on", so the fleet sat dead behind a
    # green port and a green tab until a human ran /json/activate by hand.
    check("FAULT_FROZEN is heal-able", vp.FAULT_FROZEN in vp.HEALABLE, str(vp.HEALABLE))
    check("...and FAULT_OTHER still is not", vp.FAULT_OTHER not in vp.HEALABLE)
    check("a cdp command timeout reads as frozen",
          vp.is_frozen(TimeoutError("Runtime.evaluate did not answer within 60s")))
    check("a login wall does not", not vp.is_frozen(RuntimeError("no session token in the page")))
    check("neither does an ordinary failure", not vp.is_frozen(RuntimeError("connection refused")))
    # A urllib read timeout IS a TimeoutError, so classifying on the type alone would file "the
    # provider's own server was slow" as "this tab cannot run JavaScript" and reload a healthy tab.
    check("a network read timeout is not frozen either",
          not vp.is_frozen(socket.timeout("timed out")), repr(socket.timeout is TimeoutError))
    frozen = vr.Fleet([vp.Account("flow", 39998, "z1")])
    z1 = frozen.accounts[0]
    z1.ready, z1.fault, z1.reason = False, vp.FAULT_FROZEN, "tab is not executing JS"
    rec = frozen._heal_one(z1)
    check("a frozen tab routes to activate, not to a relaunch",
          rec and rec["action"] == "activate", str(rec and rec["action"]))
    check("...and waking it never touches the launch backoff",
          not frozen._heal_after and frozen._wake_fails.get(z1.key) == 1,
          f"launch={dict(frozen._heal_after)} wake_fails={dict(frozen._wake_fails)}")
    allowed, wait = frozen._may_wake(z1)
    check("a wake that failed arms its own backoff", not allowed and wait > 0, f"{wait:.0f}s")
    frozen._arm_wake(z1, ok=False)
    allowed, wait = frozen._may_wake(z1)
    check("consecutive wake failures double the wait",
          not allowed and wait >= vr.HEAL_BACKOFF_MIN * 2 - 5, f"{wait:.0f}s")
    # A frozen tab and a dead Chrome on the SAME port must not share a penalty box: the cheap HTTP
    # activation of one tab should not be frozen out for half an hour because Chrome refuses to start.
    shared = vr.Fleet([vp.Account("flow", 39997, "s-flow"), vp.Account("rtst", 39997, "s-rtst")])
    shared._arm_backoff(39997, ok=False)
    shared._arm_backoff(39997, ok=False)
    allowed_w, _ = shared._may_wake(shared.accounts[1])
    check("a Chrome that will not launch does not block waking a sibling tab", allowed_w,
          f"launch backoff={ {k: round(v) for k, v in shared._heal_after.items()} }")
    z1.lock.acquire()
    rec = frozen._heal_one(z1)
    check("a frozen tab is still never woken under a running job",
          rec and rec["action"] == "skip" and "busy" in rec["detail"],
          str(rec and rec["detail"])[:60])
    z1.lock.release()

    print("\n-- registry: the Flow-only file migrates, and is never written to ---------")
    import pathlib as _pl, shutil as _sh, tempfile as _tf
    tmp = _pl.Path(_tf.mkdtemp(prefix="vr-smoke-"))
    keep = (vr.STATE, vr.ACCOUNTS_FILE, vr.LEGACY_ACCOUNTS_FILE)
    try:
        vr.STATE, vr.ACCOUNTS_FILE = tmp, tmp / "video_accounts.json"
        vr.LEGACY_ACCOUNTS_FILE = tmp / "flow_accounts.json"
        # Exactly the real file's shape: one entry, no "provider" key at all.
        old = {"accounts": [{"label": "pro-1", "port": 9222, "enabled": True}]}
        vr.LEGACY_ACCOUNTS_FILE.write_text(json.dumps(old), encoding="utf-8")
        before = vr.LEGACY_ACCOUNTS_FILE.read_bytes()
        fleet = vr.load_accounts()
        check("a provider-less entry loads as flow",
              len(fleet.accounts) == 1 and fleet.accounts[0].provider == "flow"
              and fleet.accounts[0].label == "pro-1", str(fleet.accounts[0].public()))
        check("the new registry file was written", vr.ACCOUNTS_FILE.exists())
        migrated = json.loads(vr.ACCOUNTS_FILE.read_text(encoding="utf-8"))
        check("every migrated entry carries provider/profile/url keys",
              all({"provider", "profile", "url"} <= set(e) for e in migrated["accounts"]),
              str(migrated["accounts"])[:90])
        check("the Flow-only file was left byte-for-byte alone",
              vr.LEGACY_ACCOUNTS_FILE.read_bytes() == before)
        fleet.accounts[0].url = "https://labs.google/fx/tools/flow/project/deadbeef"
        check("a probed url is written back for recovery", fleet.save_urls()
              and "deadbeef" in vr.ACCOUNTS_FILE.read_text(encoding="utf-8"))
        check("...and an unchanged fleet rewrites nothing", not fleet.save_urls())
    finally:
        vr.STATE, vr.ACCOUNTS_FILE, vr.LEGACY_ACCOUNTS_FILE = keep
        _sh.rmtree(tmp, ignore_errors=True)

    print("\n-- the ledger: a rehearsal never lands in the money log -------------------")
    # MEASURED 2026-08-24: 40 dry-run records had accumulated in video_jobs.jsonl, all
    # status=succeeded with credits_charged=0 and a borrowed file path. An integrator reading that
    # file -- or Jobs.load() replaying it -- could not tell them from paid work.
    now = LEDGER.read_bytes() if LEDGER.exists() else b""
    check("video_jobs.jsonl is byte-for-byte unchanged by a dry-run run",
          now == LEDGER_BEFORE, f"{len(LEDGER_BEFORE)} -> {len(now)} bytes")
    check("...because rehearsals go to their own log",
          DRY_LEDGER.exists() and DRY_LEDGER.stat().st_size > DRY_BEFORE,
          f"{DRY_LEDGER.name} grew {DRY_LEDGER.stat().st_size - DRY_BEFORE}B"
          if DRY_LEDGER.exists() else "MISSING")
    check("...and the money log is not what Jobs.load() would call history",
          vr.DRYRUN_JOBS_FILE not in (vr.JOBS_FILE, vr.LEGACY_JOBS_FILE),
          vr.DRYRUN_JOBS_FILE.name)
finally:
    srv.terminate()
    try:
        out = srv.communicate(timeout=15)[0]
    except Exception:
        srv.kill()
        out = ""

print("\n" + "=" * 74)
print("FAILED: " + ", ".join(fails) if fails else "ALL SMOKE CHECKS PASSED (0 credits spent)")
print("=" * 74)
if "ya29." in out or "AIza" in out:
    print("!! server log contained a secret-shaped string")
sys.exit(1 if fails else 0)
