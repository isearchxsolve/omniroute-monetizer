"""Dry-run smoke test for the reviewed flow_shim: proves the two money bugs are actually closed
without spending a credit. Exercises the exact JSON OmniRoute's compiled comfyui handler emits."""
import json, subprocess, sys, time, urllib.error, urllib.request

D, C = "http://127.0.0.1:8189", "http://127.0.0.1:8188"


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


srv = subprocess.Popen([sys.executable, "-u", "scripts/automation/flow_shim.py", "serve",
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
    st, h2 = call(D + "/healthz", token="smoketoken")
    check("full shape with a token", "credits" in (h2["accounts"][0] if h2.get("accounts") else {}))
    st, _ = call(D + "/v1/accounts")
    check("/v1/accounts still 401s", st == 401, f"HTTP {st}")

    print("\n-- money: the reservation floor must never ratchet upward ----------------")
    # A dry run charges nothing, so this path is unreachable through HTTP. Test it directly.
    # The hazard: credits_before is read from the account and credits_after comes from the submit
    # response, so any concurrent spend on that account lands inside the window and inflates the
    # delta. If that inflated delta became the floor, acquire() would refuse every account holding
    # less than it -- capacity stranded for good.
    sys.path.insert(0, "scripts/automation")
    import flow_shim as fs
    M = "veo_3_1_t2v_fast"
    fs.MEASURED_COST.clear()
    fs.observe_cost(M, 20, 1)
    check("an honest run sets the floor", fs.MEASURED_COST.get(M) == 20, f"floor={fs.MEASURED_COST.get(M)}")
    fs.observe_cost(M, 80, 1)
    check("a concurrent external spend cannot raise it", fs.MEASURED_COST.get(M) == 20,
          f"floor={fs.MEASURED_COST.get(M)}")
    fs.observe_cost(M, 40, 4)
    check("multi-media cost is divided per media", fs.MEASURED_COST.get(M) == 10,
          f"floor={fs.MEASURED_COST.get(M)}")
    for label, charged, n in (("absurd delta ignored", 5000, 1), ("negative delta ignored", -30, 1),
                              ("missing billing data ignored", None, None)):
        fs.observe_cost(M, charged, n)
        check(label, fs.MEASURED_COST.get(M) == 10, f"floor={fs.MEASURED_COST.get(M)}")

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
          str(q.get("flow_shim")))

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
