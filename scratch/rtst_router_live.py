"""Prove rtst end to end THROUGH THE ROUTER, over the same HTTP face the filmmaking app will use.

SPENDS REAL CREDITS: one vidu clip, 3s @540p, quoted at 6 of the account's 24. Nothing here retries a
submit -- if any step after the submit fails, the credits are already gone and a second attempt would
spend 6 more, so the script stops and says where it stopped.

Why this exists: state/video_jobs.jsonl had zero rtst records. rtst_client.py's own harness had proven
the provider (job 96089, 30 -> 24 credits, an mp4 on disk), but the router's own submit -> poll ->
download path had never once driven it. That seam is what the app depends on, so that seam gets proven.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path("D:/omniroute-monetizer")
LEDGER = ROOT / "state" / "video_jobs.jsonl"
DIRECT = "http://127.0.0.1:8189"
TOKEN = "livetoken"
PROMPT = ("a red paper boat drifting across a dark rain puddle at night, "
          "reflected neon signs rippling on the water as raindrops land")
REQ = {"model": "vidu", "prompt": PROMPT, "duration": 3, "resolution": 540,
       "aspect": "16:9", "audio": False}

fail = []


def call(url: str, payload=None, timeout=60):
    req = urllib.request.Request(
        url, data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {TOKEN}",
                 **({"Content-Type": "application/json"} if payload is not None else {})},
        method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            ct = r.headers.get("Content-Type", "")
            return r.status, (json.loads(body) if "json" in ct else body)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}  {detail}")
    if not ok:
        fail.append(name)
    return ok


srv = subprocess.Popen([sys.executable, "-u", "scripts/automation/video_router.py", "serve",
                        "--token", TOKEN],
                       cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    print("-- waiting for the real (NOT dry-run) serve face ------------------------")
    health = None
    for _ in range(120):
        time.sleep(0.5)
        try:
            _, health = call(DIRECT + "/healthz")
            break
        except Exception:
            continue
    if not step("serve is up", bool(health)):
        raise SystemExit("server never answered /healthz")
    step("...and it is NOT in dry-run mode", health.get("dry_run") is False,
         f"dry_run={health.get('dry_run')}")
    rtst = next((a for a in health["accounts"] if a.get("provider") == "rtst"), None)
    if not step("the rtst account is ready", bool(rtst and rtst.get("ready")), str(rtst)):
        raise SystemExit("rtst is not ready -- run doctor")
    before = rtst["credits"]
    print(f"        balance before: {before} credits")

    print("\n-- free quote first (this is what the app should always do) -------------")
    st, q = call(DIRECT + "/v1/videos/quote", REQ)
    step("quote answered 200", st == 200, str(st))
    step("quoted exactly", q.get("exact") is True and q.get("quote") == q.get("estimate"),
         f"estimate={q.get('estimate')} quote={q.get('quote')} exact={q.get('exact')}")
    step("quote is affordable", not q.get("error"), str(q.get("error")))
    quoted = q.get("quote")
    print(f"        quote: {quoted} credits, ceiling {q.get('max_spend_default')}")
    if quoted != 6:
        raise SystemExit(f"expected a 6-credit quote, got {quoted} -- not spending on a surprise")

    print(f"\n-- SUBMITTING FOR REAL: {quoted} credits, one attempt, no retry ---------")
    t0 = time.time()
    st, job = call(DIRECT + "/v1/videos/generations",
                   {**REQ, "wait": True, "wait_timeout": 900}, timeout=960)
    took = time.time() - t0
    print(f"        {st} after {took:.0f}s")
    print(json.dumps(job, indent=2)[:1400])
    step("the router routed it to rtst", job.get("provider") == "rtst", str(job.get("provider")))
    step("job succeeded", job.get("status") == "succeeded",
         f"status={job.get('status')} error={job.get('error')}")
    step("credits were charged, and only the quoted amount",
         job.get("credits_charged") == quoted,
         f"before={job.get('credits_before')} charged={job.get('credits_charged')} "
         f"after={job.get('credits_after')}")
    step("media landed on disk", bool(job.get("file")) and (job.get("bytes_total") or 0) > 0,
         f"{job.get('bytes_total')}B -> {job.get('file')}")
    if job.get("file"):
        step("...and the file is really there",
             pathlib.Path(job["file"]).exists()
             and pathlib.Path(job["file"]).stat().st_size == job.get("bytes_total"))

    print("\n-- the app's download route -------------------------------------------")
    url = job.get("content_url")
    step("the job carries a content_url", bool(url), str(url))
    if url:
        st, body = call(DIRECT + url, timeout=180)
        step("content route served the bytes", st == 200 and isinstance(body, bytes),
             f"{st}, {len(body) if isinstance(body, bytes) else '?'}B")
        if isinstance(body, bytes):
            step("...byte count matches the job record", len(body) == job.get("bytes_total"),
                 f"{len(body)} vs {job.get('bytes_total')}")
            step("...and it is an mp4", body[4:8] == b"ftyp", repr(body[:12]))
            out = ROOT / "state" / "harvest" / "rtst" / f"router_{job['id'][:8]}.mp4"
            out.write_bytes(body)
            print(f"        saved a copy to {out}")

    print("\n-- the ledger --------------------------------------------------------")
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    mine = [r for r in rows if r.get("id") == job.get("id")]
    step("the money ledger now holds this job", bool(mine), f"{len(rows)} record(s) total")
    step("...recorded against provider rtst",
         any(r.get("provider") == "rtst" for r in mine))
    step("...with no dry_run flag", all(not r.get("dry_run") for r in mine))

    _, health2 = call(DIRECT + "/healthz")
    r2 = next((a for a in health2["accounts"] if a.get("provider") == "rtst"), {})
    step("the live balance dropped by exactly the quote", r2.get("credits") == before - quoted,
         f"{before} -> {r2.get('credits')}")
finally:
    srv.terminate()
    try:
        out = srv.communicate(timeout=20)[0]
    except Exception:
        srv.kill()
        out = ""
    tail = [l for l in (out or "").splitlines() if l.strip()][-12:]
    if tail:
        print("\n-- server log tail ---------------------------------------------------")
        for l in tail:
            print("   " + l)

print("\n" + "=" * 72)
print("FAILED: " + ", ".join(fail) if fail else "rtst PROVEN END TO END THROUGH THE ROUTER")
print("=" * 72)
sys.exit(1 if fail else 0)
