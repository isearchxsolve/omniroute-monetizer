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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from session_pool import SessionPool, ChatError

# Initialize global pool
pool = SessionPool()

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
        
        try:
            # Route based on detected modality
            result = pool.chat(messages, model=model, modality=modality, host=host_target)
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
    server = ExclusiveThreadingHTTPServer(("127.0.0.1", port), ShimHandler)
    print(f"SessionPool Shim listening on http://127.0.0.1:{port}/v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8190
    run(port)
