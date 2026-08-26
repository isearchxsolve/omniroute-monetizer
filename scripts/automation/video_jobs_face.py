"""video_jobs_face.py -- the :8189 HTTP face that speaks oioi's FROZEN async video contract.

WHY THIS FILE EXISTS (read before touching):
  The video SUPPLY engine already exists -- `session_pool.py` routes `modality="video"` to
  `VideoUniversalSessionClient`, which does the sentinel string-swap replay (capture a genuine
  signed request carrying "Reply exactly one word: Omni.", then `.replace()` the sentinel with the
  real prompt and re-send). There is NO per-provider adapter and NO reverse-engineering of cookies.
  `session_pool_shim.py` already serves that engine over HTTP on :8190 as `/v1/chat/completions`.

  The one thing that did NOT exist is a face speaking oioi's frozen ASYNC contract:
      POST   /v1/video/jobs            submit  -> 202 {jobId,provider,...} | 200 idempotent | 503 no_capacity
      GET    /v1/video/jobs/{id}       poll    -> {jobId,status,provider,progress,url,error,creditsSpent}
      GET    /v1/video/capacity        supply  -> {seats:[...], totalClipsAvailable}
      DELETE /v1/video/jobs/{id}       cancel  -> 2xx
      GET    /v1/video/jobs/{id}/content        the fetchable clip bytes (our own origin)
  (Contract source of truth: oioi backend/film_pipeline/clients.py::VideoRouterClient + models.py.)

  This file is ONLY that face. The engine underneath is `session_pool`, deliberately NOT the
  `video_provider.py` normalise/estimate/confirm/submit stack (that is the wrong engine for the
  replay supply path). `video_router.py`'s own :8189 routes are `/v1/videos/generations` -- a
  DIFFERENT shape; this face does not touch it, and answers /healthz so the keepalive task treats
  :8189 as already-served and does not double-bind the old router.

Money safety:
  - jobKey idempotency: a repeat POST with a seen jobKey returns the SAME job (200), never a second
    submit -- the double-charge backstop, mirrored on top of oioi's own UNIQUE(job_key).
  - We never pay, never solve a wall/captcha. If a provider surfaces a wall, we report it as an
    `error` beginning "wall:" so oioi PARKS the seat -- we do not cross it.

Run:
    python video_jobs_face.py                       # bind 127.0.0.1:8189, real session_pool engine
    python video_jobs_face.py --engine stub         # same face, canned engine (no live seats)
    python video_jobs_face.py --selftest            # hermetic contract smoke test, exits 0 on PASS
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import uuid
import pathlib
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# scripts/automation imports its siblings by bare module name; keep that working when launched from
# any cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATE = pathlib.Path(r"D:\omniroute-monetizer\state\video_jobs.json")
DEFAULT_PORT = 8189
NO_CAPACITY_RETRY = 120                 # seconds; the retryAfterSeconds we hand oioi on a dry pool
VIDEO_STATUS = {"queued", "running", "succeeded", "failed"}
_JOBID = re.compile(r"^/v1/video/jobs/([0-9a-f]{32})$")
_CONTENT = re.compile(r"^/v1/video/jobs/([0-9a-f]{32})/content$")


def _log(msg: str) -> None:
    print(f"[video-jobs] {msg}", flush=True)


# --------------------------------------------------------------------------------------------------
# Engine abstraction. The face never imports the replay stack directly and never sees a provider
# exception -- an Engine.generate() ALWAYS returns a normalised dict, so the HTTP layer stays clean
# and the smoke test needs zero heavy deps.
#
#   generate(...) success -> {"ok": True,  "provider": str, "url": str|None,
#                             "inline_bytes": bytes|None, "content_type": str, "credits": float}
#   generate(...) failure -> {"ok": False, "provider": str, "error": str}   # error: "wall:"/"auth:"/plain
#   seats() -> [ {"seat","provider","creditsRemaining","clipsRemaining","cooldownUntil"} , ... ]
#   has_capacity() -> bool
# --------------------------------------------------------------------------------------------------
class PoolEngine:
    """Production engine: the existing session_pool replay path, modality='video'."""

    name = "pool"

    def __init__(self) -> None:
        from session_pool import SessionPool          # lazy: only real mode pays the import
        self.pool = SessionPool()

    def _live(self):
        return self.pool.live(modality="video")

    def has_capacity(self) -> bool:
        return bool(self._live())

    def seats(self):
        out = []
        for s in self._live():
            cooldown = getattr(s, "cooldown_until", 0.0) or 0.0
            out.append({
                "seat": s.key,
                "provider": s.host,
                # we do not track per-seat credits precisely here; report an honest floor of 1 clip
                # per live dispatchable seat so oioi sees capacity>0 iff a seat can actually answer.
                "creditsRemaining": 0.0,
                "clipsRemaining": 1,
                "cooldownUntil": (cooldown if cooldown > time.time() else None),
            })
        return out

    def generate(self, *, prompt, aspect_ratio, duration, image_refs, seed):
        try:
            from veo_session_replay import SessionExpired
        except Exception:                              # pragma: no cover - defensive
            class SessionExpired(Exception):
                pass
        try:
            from veoaifree_chat_client import ChatError
        except Exception:                              # pragma: no cover - defensive
            class ChatError(Exception):
                pass
        try:
            r = self.pool.chat(
                [{"role": "user", "content": prompt}],
                modality="video",
                aspect_ratio=aspect_ratio,
                duration=duration,
                image_refs=image_refs,
                seed=seed,
            )
            url = r.get("text")
            if not url:
                return {"ok": False, "provider": r.get("provider") or "pool",
                        "error": "video engine returned no url"}
            return {"ok": True, "provider": r.get("provider") or "pool", "url": url,
                    "inline_bytes": None, "content_type": "video/mp4", "credits": 0.0}
        except SessionExpired:
            # seat credential is dead -> oioi must park THIS seat (auth:), not fail the clip globally.
            return {"ok": False, "provider": "pool", "error": "auth: session expired"}
        except ChatError as e:
            msg = " ".join(str(a) for a in getattr(e, "args", ())) or str(e) or "video error"
            low = msg.lower()
            if low.startswith("wall:"):
                return {"ok": False, "provider": "pool", "error": msg}          # never cross a wall
            if "timeout" in low:
                return {"ok": False, "provider": "pool", "error": "video generation timed out"}
            return {"ok": False, "provider": "pool", "error": msg}              # transient
        except Exception as e:                          # pragma: no cover - defensive
            return {"ok": False, "provider": "pool", "error": (str(e) or "video job failed")}


class StubEngine:
    """Canned engine for the hermetic smoke test -- no live seats, no network, zero credits.

    Prompt hooks let one server exercise every branch:
      contains 'FAILAUTH'    -> auth: failure   (seat cred dead)
      contains 'FAILWALL'    -> wall: failure   (paywall; oioi parks, never retries)
      contains 'FAILTIMEOUT' -> transient timeout
    """

    name = "stub"

    def __init__(self, *, delay: float = 0.15, capacity: bool = True) -> None:
        self.delay = delay
        self.capacity = capacity

    def has_capacity(self) -> bool:
        return self.capacity

    def seats(self):
        if not self.capacity:
            return []
        return [{"seat": "stub-seat-1", "provider": "stub.test",
                 "creditsRemaining": 120.0, "clipsRemaining": 4, "cooldownUntil": None}]

    def generate(self, *, prompt, aspect_ratio, duration, image_refs, seed):
        time.sleep(self.delay)
        p = (prompt or "").upper()
        if "FAILAUTH" in p:
            return {"ok": False, "provider": "stub.test", "error": "auth: session expired"}
        if "FAILWALL" in p:
            return {"ok": False, "provider": "stub.test", "error": "wall: credits exhausted"}
        if "FAILTIMEOUT" in p:
            return {"ok": False, "provider": "stub.test", "error": "video generation timed out"}
        # a tiny but real MP4 'ftyp' header so content-type sniffing sees video bytes
        blob = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isomstub-clip"
        return {"ok": True, "provider": "stub.test", "url": None, "inline_bytes": blob,
                "content_type": "video/mp4", "credits": 30.0}


# --------------------------------------------------------------------------------------------------
# Job store. Persists CONTRACT-SAFE fields only (id/jobKey/status/provider/progress/url/error/
# creditsSpent/timestamps). Run params (the prompt etc.) and media (bytes or the provider's signed
# url) stay in memory -- we never persist a signed media url or a credential to disk.
# --------------------------------------------------------------------------------------------------
class JobStore:
    _PERSIST = ("id", "jobKey", "status", "provider", "progress", "url", "error",
                "creditsSpent", "estimatedSeconds", "creditsReserved", "created", "updated")

    def __init__(self, path: pathlib.Path = STATE):
        self.path = path
        self.lock = threading.Lock()
        self.jobs = {}                     # job_id -> public dict (persisted)
        self.by_key = {}                   # jobKey -> job_id
        self.params = {}                   # job_id -> run params (memory only)
        self.media = {}                    # job_id -> {"bytes":..,"url":..,"ct":..} (memory only)
        self.cancelled = set()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        for job in data.get("jobs", []):
            jid = job.get("id")
            if not jid:
                continue
            self.jobs[jid] = job
            if job.get("jobKey"):
                self.by_key[job["jobKey"]] = jid

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            slim = [{k: j.get(k) for k in self._PERSIST} for j in self.jobs.values()]
            self.path.write_text(json.dumps({"jobs": slim}, indent=2), encoding="utf-8")
        except Exception:
            pass                            # best-effort; idempotency still holds within the run

    def get(self, job_id):
        return self.jobs.get(job_id)

    def get_by_key(self, job_key):
        jid = self.by_key.get(job_key)
        return self.jobs.get(jid) if jid else None

    def create(self, *, job_key, provider, prompt, aspect_ratio, duration, image_refs, seed):
        """Caller MUST hold self.lock. Creates the queued job atomically under the key."""
        job_id = uuid.uuid4().hex
        now = time.time()
        job = {"id": job_id, "jobKey": job_key, "status": "queued", "provider": provider,
               "progress": 0.0, "url": None, "error": None, "creditsSpent": 0.0,
               "estimatedSeconds": int(duration or 0), "creditsReserved": 0.0,
               "created": now, "updated": now}
        self.jobs[job_id] = job
        self.by_key[job_key] = job_id
        self.params[job_id] = {"prompt": prompt, "aspect_ratio": aspect_ratio,
                               "duration": duration, "image_refs": image_refs, "seed": seed}
        self._save()
        return job

    def update(self, job_id, **fields):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            job.update(fields)
            job["updated"] = time.time()
            self._save()
            return job

    def set_media(self, job_id, *, url=None, blob=None, ct="video/mp4"):
        self.media[job_id] = {"url": url, "bytes": blob, "ct": ct}


# module-level singletons wired in main()/selftest
STORE: JobStore
ENGINE = None
PUBLIC_BASE = f"http://127.0.0.1:{DEFAULT_PORT}"


def run_job(job_id: str) -> None:
    """Drive one job through the engine and map the result onto the frozen status enum."""
    params = STORE.params.get(job_id, {})
    STORE.update(job_id, status="running", progress=0.05)
    t0 = time.time()
    try:
        out = ENGINE.generate(
            prompt=params.get("prompt", ""),
            aspect_ratio=params.get("aspect_ratio", "16:9"),
            duration=params.get("duration", 5),
            image_refs=params.get("image_refs", []),
            seed=params.get("seed"),
        )
    except Exception as e:                              # engine promised not to raise; belt-and-braces
        out = {"ok": False, "provider": "pool", "error": (str(e) or "video job failed")}

    if job_id in STORE.cancelled:
        return                                          # cancel won the race; leave the cancelled state
    ms = int((time.time() - t0) * 1000)
    if out.get("ok"):
        STORE.set_media(job_id, url=out.get("url"), blob=out.get("inline_bytes"),
                        ct=out.get("content_type", "video/mp4"))
        public_url = f"{PUBLIC_BASE}/v1/video/jobs/{job_id}/content"
        STORE.update(job_id, status="succeeded", progress=1.0, url=public_url,
                     provider=out.get("provider") or STORE.jobs[job_id]["provider"],
                     creditsSpent=float(out.get("credits") or 0.0))
        _log(f"job {job_id[:8]} succeeded provider={out.get('provider')} {ms}ms")
    else:
        STORE.update(job_id, status="failed", progress=1.0,
                     provider=out.get("provider") or STORE.jobs[job_id]["provider"],
                     error=(out.get("error") or "video job failed"))
        _log(f"job {job_id[:8]} failed error={out.get('error')!r} {ms}ms")


class Handler(BaseHTTPRequestHandler):
    server_version = "OmniVideoJobs/1.0"
    protocol_version = "HTTP/1.1"

    # -- helpers --------------------------------------------------------------------------------
    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return None

    def log_message(self, *a):                          # silence stdlib access log; we log our own
        return

    # -- job doc -> frozen contract shape -------------------------------------------------------
    @staticmethod
    def _job_view(job):
        return {"jobId": job["id"], "status": job["status"],
                "provider": job.get("provider") or "unknown",
                "progress": float(job.get("progress") or 0.0),
                "url": job.get("url"), "error": job.get("error"),
                "creditsSpent": float(job.get("creditsSpent") or 0.0)}

    # -- routes ---------------------------------------------------------------------------------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/healthz", "/health"):
            return self._json(200, {"status": "ok", "face": "video-jobs",
                                    "engine": getattr(ENGINE, "name", "?")})
        if path == "/v1/video/capacity":
            seats = ENGINE.seats()
            total = sum(int(s.get("clipsRemaining") or 0) for s in seats)
            return self._json(200, {"seats": [
                {"seat": str(s["seat"]), "provider": str(s["provider"]),
                 "creditsRemaining": float(s.get("creditsRemaining") or 0),
                 "clipsRemaining": int(s.get("clipsRemaining") or 0),
                 "cooldownUntil": s.get("cooldownUntil")} for s in seats],
                "totalClipsAvailable": total})
        m = _CONTENT.match(path)
        if m:
            return self._serve_content(m.group(1))
        m = _JOBID.match(path)
        if m:
            job = STORE.get(m.group(1))
            if not job:
                return self._json(404, {"error": "unknown job"})
            return self._json(200, self._job_view(job))
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/v1/video/jobs":
            return self._json(404, {"error": "not found"})
        data = self._read_json()
        if data is None:
            return self._json(400, {"error": "invalid json"})
        job_key = str(data.get("jobKey") or "").strip()
        prompt = str(data.get("prompt") or "")
        if not job_key or not prompt:
            return self._json(400, {"error": "jobKey and prompt are required"})

        with STORE.lock:
            existing = STORE.get_by_key(job_key)
            if existing:
                # idempotent replay -- the double-charge backstop. 200, same job, no new submit.
                return self._json(200, {"jobId": existing["id"],
                                        "provider": existing.get("provider") or "unknown",
                                        "estimatedSeconds": int(existing.get("estimatedSeconds") or 0),
                                        "creditsReserved": float(existing.get("creditsReserved") or 0)})
            if not ENGINE.has_capacity():
                return self._json(503, {"error": "no_capacity",
                                        "retryAfterSeconds": NO_CAPACITY_RETRY})
            seats = ENGINE.seats()
            provider_guess = seats[0]["provider"] if seats else "pool"
            job = STORE.create(
                job_key=job_key, provider=provider_guess, prompt=prompt,
                aspect_ratio=str(data.get("aspectRatio") or "16:9"),
                duration=int(data.get("durationSeconds") or 5),
                image_refs=list(data.get("imageRefs") or []),
                seed=data.get("seed"),
            )

        threading.Thread(target=run_job, args=(job["id"],), daemon=True).start()
        return self._json(202, {"jobId": job["id"], "provider": provider_guess,
                                "estimatedSeconds": int(job.get("estimatedSeconds") or 0),
                                "creditsReserved": 0.0})

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        m = _JOBID.match(path)
        if not m:
            return self._json(404, {"error": "not found"})
        job = STORE.get(m.group(1))
        if not job:
            return self._json(404, {"error": "unknown job"})
        if job["status"] in ("queued", "running"):
            STORE.cancelled.add(job["id"])
            STORE.update(job["id"], status="failed", error="cancelled", progress=1.0)
        return self._json(200, {"cancelled": True})

    def _serve_content(self, job_id):
        job = STORE.get(job_id)
        if not job:
            return self._json(404, {"error": "unknown job"})
        if job.get("status") != "succeeded":
            return self._json(409, {"error": "job not succeeded"})
        media = STORE.media.get(job_id)
        if not media:
            return self._json(410, {"error": "media not available (server restarted)"})
        blob = media.get("bytes")
        if blob is None and media.get("url"):
            # proxy-fetch the provider clip through our origin (public urls; cookie-gated seats are a
            # live-mode enhancement -- would thread the seat jar here).
            try:
                with urllib.request.urlopen(media["url"], timeout=60) as r:
                    blob = r.read()
                    media["ct"] = r.headers.get("Content-Type") or media.get("ct") or "video/mp4"
            except Exception as e:
                return self._json(502, {"error": f"clip fetch failed: {type(e).__name__}"})
        if not blob:
            return self._json(502, {"error": "empty clip"})
        self.send_response(200)
        self.send_header("Content-Type", media.get("ct") or "video/mp4")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


def serve(bind: str, port: int, engine, public_base=None):
    global STORE, ENGINE, PUBLIC_BASE
    STORE = JobStore()
    ENGINE = engine
    PUBLIC_BASE = public_base or f"http://{'127.0.0.1' if bind in ('', '0.0.0.0') else bind}:{port}"
    httpd = ThreadingHTTPServer((bind, port), Handler)
    _log(f"listening on {bind}:{port}  engine={engine.name}  public_base={PUBLIC_BASE}")
    _log("oioi film kit -> POST http://127.0.0.1:8189/v1/video/jobs (frozen async contract)")
    httpd.serve_forever()


# --------------------------------------------------------------------------------------------------
# Hermetic contract smoke test: spins the real server on ephemeral ports with StubEngine and drives
# the full contract over real HTTP. Zero live seats, zero credits, no network.
# --------------------------------------------------------------------------------------------------
def _selftest() -> int:
    global STORE, ENGINE, PUBLIC_BASE
    import http.client

    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail else ''}", flush=True)

    def spin(engine, port):
        STORE = JobStore(path=pathlib.Path(os.devnull))     # don't touch the real state file
        ENGINE = engine
        PUBLIC_BASE = f"http://127.0.0.1:{port}"
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        # rebind module globals the handler/run_job read
        globals()["STORE"], globals()["ENGINE"], globals()["PUBLIC_BASE"] = STORE, ENGINE, PUBLIC_BASE
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd

    def req(port, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if payload else {}
        c.request(method, path, payload, headers)
        r = c.getresponse()
        raw = r.read()
        c.close()
        ct = r.getheader("Content-Type") or ""
        parsed = json.loads(raw) if raw and "json" in ct else raw
        return r.status, parsed

    def poll(port, job_id, want_terminal=("succeeded", "failed"), timeout=8.0):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            st, doc = req(port, "GET", f"/v1/video/jobs/{job_id}")
            last = doc
            if isinstance(doc, dict) and doc.get("status") in want_terminal:
                return doc
            time.sleep(0.1)
        return last

    print("video_jobs_face selftest -- hermetic, StubEngine, no live seats\n", flush=True)

    # --- server A: healthy capacity -----------------------------------------------------------
    PORT_A = 8991
    spin(StubEngine(delay=0.1, capacity=True), PORT_A)

    st, doc = req(PORT_A, "GET", "/healthz")
    check("healthz 200", st == 200 and isinstance(doc, dict) and doc.get("status") == "ok", f"status={st}")

    st, doc = req(PORT_A, "GET", "/v1/video/capacity")
    ok = (st == 200 and isinstance(doc, dict) and doc.get("seats")
          and doc.get("totalClipsAvailable", 0) > 0
          and {"seat", "provider", "creditsRemaining", "clipsRemaining", "cooldownUntil"}
          <= set(doc["seats"][0].keys()))
    check("capacity shape + >0", ok, f"total={doc.get('totalClipsAvailable') if isinstance(doc, dict) else '?'}")

    submit = {"jobKey": "film1:shot1", "prompt": "a red balloon drifts over a grey city",
              "durationSeconds": 5, "imageRefs": [], "aspectRatio": "16:9", "seed": None}
    st, doc = req(PORT_A, "POST", "/v1/video/jobs", submit)
    ok = st == 202 and isinstance(doc, dict) and doc.get("jobId") and doc.get("provider")
    check("submit -> 202 {jobId,provider}", ok, f"status={st} keys={list(doc) if isinstance(doc, dict) else doc}")
    job_id = doc.get("jobId") if isinstance(doc, dict) else None

    st, doc2 = req(PORT_A, "POST", "/v1/video/jobs", submit)
    ok = st == 200 and isinstance(doc2, dict) and doc2.get("jobId") == job_id
    check("idempotent replay -> 200 same jobId", ok, f"status={st} same={doc2.get('jobId') == job_id}")

    final = poll(PORT_A, job_id, want_terminal=("succeeded",))
    ok = isinstance(final, dict) and final.get("status") == "succeeded" and final.get("url") \
        and final.get("provider") and final.get("status") in VIDEO_STATUS
    check("poll -> succeeded {url,provider}", ok,
          f"status={final.get('status') if isinstance(final, dict) else final} url={bool(final.get('url')) if isinstance(final, dict) else False}")

    if isinstance(final, dict) and final.get("url"):
        u = urllib.parse.urlparse(final["url"])
        st, blob = req(PORT_A, "GET", u.path)
        ok = st == 200 and isinstance(blob, (bytes, bytearray)) and len(blob) > 0
        check("content url is fetchable bytes", ok, f"status={st} bytes={len(blob) if isinstance(blob, (bytes, bytearray)) else 0}")
    else:
        check("content url is fetchable bytes", False, "no url to fetch")

    # --- failure classifications (auth/wall/transient) ---------------------------------------
    for tag, hook, want_prefix in (("auth", "FAILAUTH", "auth:"),
                                   ("wall", "FAILWALL", "wall:"),
                                   ("transient", "FAILTIMEOUT", None)):
        s = {"jobKey": f"film1:fail:{tag}", "prompt": f"{hook} scene", "durationSeconds": 5,
             "imageRefs": [], "aspectRatio": "16:9", "seed": 1}
        st, d = req(PORT_A, "POST", "/v1/video/jobs", s)
        fin = poll(PORT_A, d.get("jobId"), want_terminal=("failed",)) if isinstance(d, dict) else None
        err = (fin or {}).get("error", "") if isinstance(fin, dict) else ""
        if want_prefix:
            ok = isinstance(fin, dict) and fin.get("status") == "failed" and err.lower().startswith(want_prefix)
        else:  # transient: failed, but NOT tagged wall:/auth: so oioi retries it
            ok = isinstance(fin, dict) and fin.get("status") == "failed" \
                and not err.lower().startswith(("wall:", "auth:"))
        check(f"failure classified: {tag}", ok, f"error={err!r}")

    # --- cancel -------------------------------------------------------------------------------
    s = {"jobKey": "film1:cancelme", "prompt": "slow pan of a canyon", "durationSeconds": 5,
         "imageRefs": [], "aspectRatio": "16:9", "seed": None}
    st, d = req(PORT_A, "POST", "/v1/video/jobs", s)
    st2, _ = req(PORT_A, "DELETE", f"/v1/video/jobs/{d.get('jobId')}")
    _, fin = req(PORT_A, "GET", f"/v1/video/jobs/{d.get('jobId')}")
    ok = st2 == 200 and isinstance(fin, dict) and fin.get("status") == "failed"
    check("cancel -> 2xx then failed", ok, f"delete={st2} status={fin.get('status') if isinstance(fin, dict) else fin}")

    st, d = req(PORT_A, "GET", "/v1/video/jobs/" + "0" * 32)
    check("unknown job -> 404", st == 404, f"status={st}")

    # --- server B: dry pool -> 503 no_capacity ------------------------------------------------
    PORT_B = 8992
    spin(StubEngine(capacity=False), PORT_B)
    st, doc = req(PORT_B, "POST", "/v1/video/jobs",
                  {"jobKey": "x", "prompt": "y", "durationSeconds": 5, "imageRefs": [],
                   "aspectRatio": "16:9", "seed": None})
    ok = st == 503 and isinstance(doc, dict) and doc.get("error") == "no_capacity" \
        and isinstance(doc.get("retryAfterSeconds"), int)
    check("dry pool -> 503 no_capacity", ok, f"status={st} body={doc}")

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} checks passed", flush=True)
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--engine", choices=("pool", "stub"), default="pool")
    ap.add_argument("--public-base", default=None,
                    help="origin oioi should fetch clip content from (default http://<bind>:<port>)")
    ap.add_argument("--selftest", action="store_true", help="run the hermetic contract smoke test")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    engine = StubEngine() if a.engine == "stub" else PoolEngine()
    serve(a.bind, a.port, engine, public_base=a.public_base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
