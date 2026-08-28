"""session_pool_shim.py -- HTTP face for session_pool.py

Provides an OpenAI-compatible /v1/chat/completions endpoint over the SessionPool.
Listens on port 8190 by default.

Multi-tenancy (2026-08-27, worklog #1110): if state/secrets/tenant_map.json exists, every request
must carry `Authorization: Bearer <api_key>` for a key listed there; the mapped tenant name is
tagged onto every response for per-consumer accounting. When the file is absent the endpoint stays
open (single-operator mode), exactly as before. Tenants share one pool by design -- the pool's
whole purpose is spreading every consumer's load across many providers so no single account gets
hammered; strict per-tenant seat isolation is deliberately NOT offered.
"""
import glob
import json
import logging
import os
import pathlib
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from session_pool import SessionPool, ChatError
from veo_session_replay import SessionExpired
from video_job_store import VideoJobStore

# Initialize global pool
pool = SessionPool()

# Durable video-job ledger (worklog #1134): the receipt/idempotency/reconciliation contract.
JOBS = VideoJobStore()

# Rough render budget advertised in receipts (estimate only; the status URL is authoritative).
VIDEO_EST_SECONDS = 300

# ----------------------------------------------------------------- JSON intent ----
# Worklog #1134 (OiiOii live E2E fix 1): JSON-intent session-pool/auto requests must never be
# answered with prose/empty/fenced-JSON. Detection: the OpenAI-standard response_format hint,
# or an explicit "JSON only"-style directive in the prompt (the film planner's exact wording:
# "Return JSON only ..."). When detected, the pool validates each seat's reply as strict JSON
# and fails over seats that violate the contract (session_pool.chat(strict_json=True)).
_JSON_INTENT_RE = re.compile(
    r"\bjson\s+only\b|\bonly\s+json\b|\breturn\s+valid\s+json\b|\bno\s+prose\s+outside\s+json\b",
    re.IGNORECASE)


def _wants_strict_json(req: dict) -> bool:
    rf = req.get("response_format")
    if isinstance(rf, dict) and str(rf.get("type", "")) in ("json_object", "json_schema"):
        return True
    for m in req.get("messages", []):
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, str) and _JSON_INTENT_RE.search(c):
            return True
    return False

# {"<api_key>": "<tenant_name>", ...}. Presence of this file turns auth ON for every consumer.
TENANT_MAP_PATH = pathlib.Path(r"D:\omniroute-monetizer\state\secrets\tenant_map.json")

# ------------------------------------------------------------------ hot-add ----
# One Chrome, infinite sites (worklog #1112): adding a provider must NOT require a shim
# restart. The tenant map is already re-read per request; seats now are too. Every request
# does ONE cheap stat of the secrets directory (its mtime moves on any add/remove/rename
# inside it) and only calls pool.rescan() when the directory actually changed. rescan()
# itself is a no-op for untouched files (it keeps the exact same session objects), so even
# a spurious trigger costs one glob + one stat per seat -- microseconds, zero disruption.
_RESCAN_LOCK = threading.Lock()
_dir_sig = [None]                                    # [last-seen directory signature]


def _maybe_rescan() -> None:
    try:
        st = os.stat(pool.secrets)
        sig = (st.st_mtime_ns, st.st_ctime_ns)
    except OSError:
        return
    if sig == _dir_sig[0]:
        return
    with _RESCAN_LOCK:
        if sig == _dir_sig[0]:                       # another thread already rescanned
            return
        try:
            pool.rescan()
        finally:
            _dir_sig[0] = sig


def _force_rescan() -> dict:
    with _RESCAN_LOCK:
        r = pool.rescan()
        try:
            st = os.stat(pool.secrets)
            _dir_sig[0] = (st.st_mtime_ns, st.st_ctime_ns)
        except OSError:
            pass
        return r


def _tenant_map():
    try:
        # utf-8-sig: Windows tooling (PowerShell Set-Content, Notepad) writes JSON with a BOM;
        # json.loads() chokes on it and would silently drop the whole map -> open endpoint.
        m = json.loads(TENANT_MAP_PATH.read_text(encoding="utf-8-sig"))
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


def _tenant_for(auth_header):
    """Return (tenant, None) when the caller may proceed, else (None, error_dict)."""
    m = _tenant_map()
    if not m:
        return "local", None                       # no map -> open single-operator mode
    h = (auth_header or "").strip()
    if not h.lower().startswith("bearer "):
        return None, {"message": "missing API key: send Authorization: Bearer <api_key>", "type": "unauthorized"}
    key = h[7:].strip()
    if key not in m:
        return None, {"message": "unknown API key", "type": "unauthorized"}
    return m[key], None


# ------------------------------------------------------------- video receipts ----
# Worklog #1134 (OiiOii live E2E fixes 2-4): video submits must return an IMMEDIATE durable
# receipt (job_id + status + provider/session/tenant + status URL), never block the HTTP
# connection for the whole render. The render runs in a worker thread against the durable
# ledger; the consumer polls GET /v1/video/jobs/{job_id} (or ?job_key=). Idempotency: a
# replayed job_key returns the SAME record and NEVER triggers a second render/spend.

def _job_receipt(rec: dict, tenant: str) -> dict:
    """OpenAI-shaped 202 receipt. The `video` block is the durable contract surface."""
    return {
        "id": rec["job_id"],
        "object": "chat.completion",
        "created": int(rec.get("created") or time.time()),
        "model": rec.get("model") or "video/auto",
        "provider": rec.get("provider"),
        "session": rec.get("session"),
        "tenant": tenant,
        "video": {
            "jobId": rec["job_id"],
            "job_key": rec.get("job_key"),
            "status": rec["status"],
            "provider": rec.get("provider"),
            "session": rec.get("session"),
            "url": rec.get("url"),
            "error": rec.get("error"),
            "progress": rec.get("progress") or 0.0,
            "creditsSpent": rec.get("credits_spent") or 0.0,
            "estimatedSeconds": VIDEO_EST_SECONDS,
            "statusUrl": f"/v1/video/jobs/{rec['job_id']}",
        },
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": json.dumps({
                "job_id": rec["job_id"], "status": rec["status"],
                "status_url": f"/v1/video/jobs/{rec['job_id']}",
            })},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _video_worker(job_id: str, messages: list, host: str = None) -> None:
    """Render one video job off the HTTP thread, updating the durable ledger as it goes.

    Seat selection uses the pool's own reserve() so LRU/cooldown/per-host-lock semantics are
    identical to chat routing. On seat failure we try the next live video seat (bounded by the
    live count), exactly like pool.chat() failover — but every attempt is recorded on the job.
    """
    tries = len(pool.live(modality="video", host=host)) or 1
    last_err = "no dispatchable video session"
    for _ in range(tries):
        rec = JOBS.get(job_id)
        if rec is None or rec["status"] == "cancelled":
            return
        res = pool.reserve(modality="video", host=host)
        if res is None:
            break
        s, res_at = res
        JOBS.update(job_id, status="running", provider=s.host, session=s.key,
                    started=time.time(), progress=0.1)
        try:
            r = s.chat(messages)
            url = r.get("video_url") or r.get("text")
            if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
                raise ChatError("NO_VIDEO_URL", f"{s.host} returned no video URL")
            s.last_used = time.time()
            s.cooldown_until = s.last_used + pool.cooldown
            pool._persist()
            JOBS.update(job_id, status="succeeded", url=url, progress=1.0,
                        credits_spent=float(r.get("credits_spent") or 0.0),
                        finished=time.time())
            return
        except SessionExpired as e:
            s.dead, s.last_error = True, "session_expired"
            last_err = f"{s.host}: session expired"
        except ChatError as e:
            base = max(time.time(), res_at)
            s.last_used = base
            s.cooldown_until = base + max(pool.cooldown, 30.0)
            s.last_error = str(e)[:60]
            last_err = f"{s.host}: {e}"
        except Exception as e:
            last_err = f"{s.host}: {type(e).__name__}: {e}"
    JOBS.update(job_id, status="failed", error=last_err[:300], finished=time.time())


class ShimHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        _maybe_rescan()                              # zero-restart hot-add (worklog #1112)
        tenant, err = _tenant_for(self.headers.get("Authorization"))
        if err:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": err}).encode())
            return
        if self.path == "/v1/models":
            models = [
                {"id": "session-pool/auto", "object": "model", "created": int(time.time()), "owned_by": "session_pool"},
                {"id": "video/auto", "object": "model", "created": int(time.time()), "owned_by": "session_pool"}
            ]
            # List all hosts as well
            for s in pool.sessions:
                if not s.dispatchable:
                    continue
                prefix = "video/" if s.modality == "video" else ""
                models.append({
                    "id": f"{prefix}{s.host}/auto",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "session_pool"
                })
            resp = {"object": "list", "data": models}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())
            return
        # ------------------------------------------------- video job lookup (#1134) ----
        # GET /v1/video/jobs/{job_id}          — status by durable job id
        # GET /v1/video/jobs?job_key=<key>     — reconciliation by the consumer's durable key
        # GET /v1/video/jobs                   — full ledger (operator/admin)
        if self.path.startswith("/v1/video/jobs"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]     # ['v1','video','jobs',<id>?]
            qs = parse_qs(parsed.query)
            if len(parts) == 4:
                rec = JOBS.get(parts[3])
            elif qs.get("job_key"):
                rec = JOBS.get_by_key(qs["job_key"][0])
            else:
                rec = None
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"object": "list", "data": JOBS.all(),
                                             "tenant": tenant}).encode())
                return
            if rec is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "unknown job",
                                                       "type": "not_found",
                                                       "tenant": tenant}}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_job_receipt(rec, tenant)).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        _maybe_rescan()                              # zero-restart hot-add (worklog #1112)
        if self.path == "/v1/rescan":
            # Explicit admin trigger: force a seat-directory rescan NOW and report the diff.
            # Same auth gate as every other endpoint.
            tenant, err = _tenant_for(self.headers.get("Authorization"))
            if err:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": err}).encode())
                return
            r = _force_rescan()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "rescan": r,
                                         "dispatchable": len(pool.live()),
                                         "tenant": tenant}).encode())
            return
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        tenant, err = _tenant_for(self.headers.get("Authorization"))
        if err:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": err}).encode())
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        try:
            req = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
            
        messages = req.get("messages", [])
        model = req.get("model", "")
        host_target = None
        modality = "chat"
        
        if model and model.startswith("video/"):
            modality = "video"
            target_str = model.replace("video/", "")
            if target_str.endswith("/auto"):
                host_target = target_str.replace("/auto", "")
                if host_target == "auto":
                    host_target = None
            else:
                host_target = target_str if target_str != "auto" else None
            model = None
        elif model and model.endswith("/auto") and model != "session-pool/auto":
            modality = "chat"
            host_target = model.split("/")[0]
            model = None
        elif model in ("auto", "auto/best-chat", "session-pool/auto", ""):
            modality = "chat"
            model = None

        # ------------------------------------------- video: immediate durable receipt ----
        # Worklog #1134 (OiiOii live E2E fix 2+3): NEVER block the HTTP connection for the
        # render. Create the durable job record FIRST (idempotent by the consumer's job_key),
        # answer 202 with the receipt, render in a worker thread. A replayed job_key returns
        # the SAME record with 200 and never spends twice.
        if modality == "video":
            if not pool.live(modality="video", host=host_target):
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "no_capacity",
                    "message": "no dispatchable video seat right now",
                    "retryAfterSeconds": 120,
                    "tenant": tenant}).encode())
                return
            vmeta = req.get("video") if isinstance(req.get("video"), dict) else {}
            job_key = vmeta.get("job_key")
            prompt = ""
            for m in reversed(messages):
                if isinstance(m, dict) and m.get("role") == "user":
                    prompt = str(m.get("content") or "")
                    break
            rec, created = JOBS.create(job_key=job_key, prompt=prompt,
                                       model=f"video/{host_target or 'auto'}/auto",
                                       host=host_target, tenant=tenant)
            if created:
                threading.Thread(target=_video_worker,
                                 args=(rec["job_id"], messages, host_target),
                                 daemon=True).start()
            self.send_response(200 if not created else 202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_job_receipt(rec, tenant)).encode())
            return

        try:
            # Route based on detected modality. strict_json (worklog #1134, fix 1): JSON-intent
            # requests fail over any seat that answers prose/empty/fenced-JSON.
            result = pool.chat(messages, model=model, modality=modality, host=host_target,
                               strict_json=_wants_strict_json(req))
        except ChatError as e:
            # Pool exhausted (every session dead/cooling) is a RATE condition, not a server fault:
            # answer like OpenAI does so consumers can back off with Retry-After instead of
            # treating a healthy-but-busy pool as broken. (worklog #1110)
            exhausted = getattr(e, "kind", None) == "NO_LIVE_SESSION"
            self.send_response(429 if exhausted else 500)
            if exhausted:
                self.send_header("Retry-After", str(int(max(pool.cooldown, 30))))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": str(e),
                                                   "type": "pool_exhausted" if exhausted else "chat_error",
                                                   "tenant": tenant}}).encode())
            return
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": str(e), "tenant": tenant}}).encode())
            return
            
        # Format response as OpenAI chat completion
        resp = {
            "id": f"chatcmpl-{int(time.time()*1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.get("label", model),
            # Non-standard but harmless to OpenAI clients; makes pool rotation observable so a
            # consumer can verify load is actually spreading across providers/sessions.
            "provider": result.get("provider"),
            "session": result.get("session"),
            "tenant": tenant,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result.get("text", "")
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

    def do_DELETE(self):
        # ------------------------------------------------- video cancellation (#1134) ----
        # DELETE /v1/video/jobs/{job_id} — published cancellation semantics:
        #   * status=queued  -> cancelled, 200. Nothing was submitted upstream, zero spend.
        #   * status=running -> 409: the render was ALREADY submitted to the provider; we do
        #     NOT claim cancellation we cannot guarantee (upstream sites have no cancel API).
        #     The honest answer is "still running; poll the status URL."
        #   * terminal states -> 200 with the record (idempotent no-op).
        _maybe_rescan()
        tenant, err = _tenant_for(self.headers.get("Authorization"))
        if err:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": err}).encode())
            return
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 4 and parts[:3] == ["v1", "video", "jobs"]:
            rec = JOBS.get(parts[3])
            if rec is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "unknown job",
                                                       "type": "not_found",
                                                       "tenant": tenant}}).encode())
                return
            if rec["status"] == "running":
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": {"message": "render already submitted upstream; cancellation not "
                                         "guaranteed — poll the status URL",
                              "type": "conflict", "tenant": tenant},
                    "video": {"jobId": rec["job_id"], "status": rec["status"]}}).encode())
                return
            cancelled, rec = JOBS.cancel(parts[3])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_job_receipt(rec, tenant)).encode())
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Mute default access logging to match other OmniRoute scripts
        pass

class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    # ONE shim, one port (worklog #1112). http.server sets allow_reuse_address=True
    # (SO_REUSEADDR), which on Windows lets a SECOND process bind the same port -- the
    # second bind succeeds and the OS hands incoming connections to EITHER listener.
    # That is exactly how four shim instances (two of them running stale code) ended up
    # sharing :8190: requests landed on a random instance, so /v1/rescan answered 404
    # and hot-added seats appeared and disappeared per request. Exclusive binding makes
    # a duplicate start fail LOUDLY at bind time, which is also what the keepalive task's
    # "is it answering?" guard needs to stay honest.
    allow_reuse_address = False


def run(port=8190):
    try:
        server = ExclusiveThreadingHTTPServer(("127.0.0.1", port), ShimHandler)
    except OSError as e:
        # Dedup guard (worklog #1134): if a shim is ALREADY serving this port, a second launch
        # must exit cleanly as a no-op, not crash with a traceback. Combined with the keepalive
        # bat's curl health probe and the supervisor's hands-off ownership, this makes exactly
        # one shim the only stable state: healthy -> nobody relaunches; duplicate spawn -> the
        # duplicate dies quietly here.
        import errno
        if e.errno in (errno.EADDRINUSE, 10048):
            print(f"SessionPool Shim: port {port} already serving -- another instance owns it; "
                  f"exiting cleanly (dedup, worklog #1134)")
            return
        raise
    print(f"SessionPool Shim listening on http://127.0.0.1:{port}/v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8190
    run(port)
