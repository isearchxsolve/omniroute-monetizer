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
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

import requests

from session_pool import SessionPool, ChatError, _load_quarantine
from veo_session_replay import SessionExpired
from video_job_store import VideoJobStore
# The tool->prompt shim is IMPORTED, not copied. It is the piece that makes a free chat seat usable
# by an agentic client, and resolve_tool_name() inside it is the load-bearing line; a second copy on
# this port would drift from :20130's and only one of them would ever get fixed.
from chat_pool_server import (tool_instruction, parse_tool_call, looks_like_overflow,
                              TOOL_RESULT_CAP)
from omniroute_api import extract_chat_content

# Initialize global pool
pool = SessionPool()

# Durable video-job ledger (worklog #1134): the receipt/idempotency/reconciliation contract.
JOBS = VideoJobStore()

# How many seats one tools request may try before giving up. Bounded because each attempt is a real
# request to a free account: unbounded failover across 18 seats exceeded a 300s client timeout, and
# hammering seats is how they get burned. Rejected seats are cooled, so the pool converges.
TOOL_FAILOVER_TRIES = 6
# Plain chat needs a bound for the same reason tools did. Unbounded, `tries` defaults to the whole
# live list, and a request that lands on Chrome-bound seats (420s DOM renders) walks them one real
# round trip at a time -- measured after quarantining api.monica.im: plain chat went from 9.7s (a
# garbage constant) to >90s (walking the slow tail). A consumer wired to :8190 needs a bounded answer
# or a bounded error, never an open-ended hang; cooled seats mean consecutive requests converge on
# the fast ones. Raise this only alongside evidence that the tail is actually worth waiting for.
CHAT_FAILOVER_TRIES = 5

# Rough render budget advertised in receipts (estimate only; the status URL is authoritative).
VIDEO_EST_SECONDS = 300

# :8190 is the final consumer gateway.  Session-pool aliases and pinned seat routes
# are served locally; every other model name is an OmniRoute request.  A sick :20128
# must never make :8190 discovery or chat hang, so every bridge call is bounded and
# produces an explicit fallback marker rather than silently pretending the paid side
# answered.
OMNIROUTE_UPSTREAM = os.environ.get("OMNIROUTE_UPSTREAM", "http://127.0.0.1:20128").rstrip("/")
# The upstream catalog is ~9.5K rows.  1.5 seconds is enough for a warm local
# request but not a reliable first fetch after a shim restart; it made discovery
# collapse to local seat aliases while OmniRoute inference was still healthy.
OMNIROUTE_MODEL_TIMEOUT_S = 10.0
OMNIROUTE_CHAT_TIMEOUT_S = 8.0
OMNIROUTE_FALLBACK_MODEL = os.environ.get("OMNIROUTE_FALLBACK_MODEL", "frontier")
OMNI_VERIFIED_ROUTES = pathlib.Path(__file__).resolve().parents[2] / "state" / "omniroute_verified_routes.json"


def _omni_verified_model_ids() -> Optional[set[str]]:
    """Return the exact Omni model allowlist; absent file preserves pre-admission compatibility."""
    if not OMNI_VERIFIED_ROUTES.exists():
        return None
    try:
        data = json.loads(OMNI_VERIFIED_ROUTES.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            return set()  # malformed admission file fails closed
        return {str(e.get("model")) for e in entries
                if isinstance(e, dict) and e.get("state") == "ADMITTED" and e.get("modality", "chat") == "chat"
                and e.get("model")}
    except (OSError, ValueError):
        return set()


def _collapse_exact_mirrored_reply(text: str) -> str:
    """Repair a measured OmniRoute SSE terminal-frame duplication.

    The upstream can emit one completed content frame twice in the same response;
    for a Law-3 result of ``58`` the visible content is ``5858``.  This is not a
    model answer and is harmful to consumers expecting JSON, numbers, or code.
    Collapse only an *exact two-copy mirror* (never prefixes or arbitrary repeated
    fragments), keeping ordinary stream/delta handling unchanged.
    """
    if len(text) >= 2 and len(text) % 2 == 0:
        half = len(text) // 2
        # Keep normal prose/code untouched: a deliberate "haha" must not become
        # "ha".  The observed malformed terminal frame is numeric-only, which is
        # also the form used by the non-echoable Law-3 health probe.
        if text[:half] == text[half:] and text[:half].isdigit():
            return text[:half]
    return text


class OmniRouteBridge:
    """Bounded merge/forward layer for the paid OmniRoute plane.

    The endpoint is intentionally best-effort: the free/session side remains usable
    when :20128 is wedged.  This is a gateway boundary, not another service owner;
    it never restarts, mutates, or authenticates to OmniRoute management APIs.
    """

    def __init__(self, base: str = OMNIROUTE_UPSTREAM):
        self.base = base
        self._models: list[dict[str, Any]] = []
        self._models_at = 0.0
        self._refresh_at = 0.0
        self._refreshing = False
        self._models_lock = threading.Lock()
        self._last_error: Optional[str] = None

    def models(self) -> list[dict[str, Any]]:
        # Never make the consumer's discovery request wait on the upstream catalog.
        # The direct catalog is large and its refresh can transiently exceed the
        # task watchdog's three-second probe.  Return the last known snapshot (or
        # an honest empty paid snapshot on cold start) and refresh asynchronously.
        # One lock prevents a thundering herd of refresh threads at a stale boundary.
        now = time.monotonic()
        with self._models_lock:
            cached = list(self._models)
            fresh = now - self._models_at < 15.0
            retry_due = now - self._refresh_at >= 15.0
            if not fresh and retry_due and not self._refreshing:
                self._refreshing = True
                self._refresh_at = now
                threading.Thread(target=self._refresh_models, name="omni-model-refresh",
                                 daemon=True).start()
            return cached

    def _refresh_models(self) -> None:
        """Refresh the paid catalog off the HTTP request thread."""
        try:
            upstream = requests.Session()
            upstream.trust_env = False
            response = upstream.get(f"{self.base}/v1/models", timeout=OMNIROUTE_MODEL_TIMEOUT_S)
            data = response.json() if response.ok else {}
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ValueError("invalid model-list shape")
            models = [row for row in rows if isinstance(row, dict) and row.get("id")]
            with self._models_lock:
                self._models = models
                self._models_at = time.monotonic()
                self._last_error = None
        except Exception as exc:
            # Preserve the last good catalog; the status endpoint exposes the
            # failed refresh.  A cold failure honestly leaves paid rows empty.
            with self._models_lock:
                self._last_error = type(exc).__name__
        finally:
            with self._models_lock:
                self._refreshing = False

    def status(self) -> dict[str, Any]:
        with self._models_lock:
            return {"base": self.base, "reachable": self._last_error is None,
                    "lastError": self._last_error, "cachedModels": len(self._models),
                    "refreshing": self._refreshing,
                    "catalogStale": bool(self._models and time.monotonic() - self._models_at >= 15.0)}

    def chat(self, raw: bytes, auth: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        allowed = _omni_verified_model_ids()
        if allowed is not None:
            try:
                requested = json.loads(raw).get("model")
            except (TypeError, ValueError, AttributeError):
                requested = None
            if requested not in allowed:
                return None, "omniroute_route_not_admitted"
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = auth
        try:
            r = requests.post(f"{self.base}/v1/chat/completions", data=raw,
                              headers=headers, timeout=OMNIROUTE_CHAT_TIMEOUT_S)
        except Exception as exc:
            return None, f"omniroute_unreachable:{type(exc).__name__}"
        raw_text = r.text or ""
        if not r.ok:
            return None, f"omniroute_http_{r.status_code}"
        try:
            parsed = r.json()
        except ValueError:
            parsed = None
        content = extract_chat_content(parsed, raw_text)
        content = _collapse_exact_mirrored_reply(content)
        if not content:
            return None, "omniroute_empty_or_unparseable"
        # A paid route can also return an HTTP-200 credit/login wall.  Do not turn
        # that into fake success at the merged consumer boundary.
        from session_pool import wall_in_reply
        if wall_in_reply(content):
            return None, "omniroute_wall"
        if isinstance(parsed, dict) and isinstance(parsed.get("choices"), list):
            parsed.setdefault("provider", "omniroute")
            parsed.setdefault("session", None)
            parsed["x_gateway_source"] = "omniroute"
            return parsed, None
        return {
            "id": f"chatcmpl-{int(time.time() * 1000)}", "object": "chat.completion",
            "created": int(time.time()), "model": "omniroute",
            "provider": "omniroute", "session": None, "x_gateway_source": "omniroute",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }, None


omniroute = OmniRouteBridge()

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


def _tools_from_request(req: dict) -> list:
    """Normalise an OpenAI tools array into the Anthropic shape the shared shim helpers read.

    :8190 is the OpenAI-compatible face, so consumers send
        {"type": "function", "function": {"name", "description", "parameters"}}
    while render_tools()/resolve_tool_name() -- shared with :20130 -- read
        {"name", "description", "input_schema"}
    Converting here keeps ONE tool contract behind both ports.
    """
    out = []
    for t in req.get("tools") or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else t
        name = fn.get("name")
        if not name:
            continue
        out.append({"name": name,
                    "description": fn.get("description") or "",
                    "input_schema": fn.get("parameters") or fn.get("input_schema") or {}})
    return out


def _flatten_tool_history(messages: list) -> list:
    """Render OpenAI tool traffic into plain text turns.

    A replayed chat UI has no native tool transcript. If the assistant's `tool_calls` and the
    `role: "tool"` results are dropped, the seat's next turn arrives with its own call and the
    output both missing -- it sees itself having said nothing and repeats the same call forever.
    Same reasoning as flatten() on :20130, applied to the OpenAI message shape.
    """
    out = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "tool":
            body = str(m.get("content") or "")[:TOOL_RESULT_CAP]
            label = m.get("name") or m.get("tool_call_id") or "tool"
            out.append({"role": "user", "content": f"[result of {label}]\n{body}"})
            continue
        if role == "assistant" and m.get("tool_calls"):
            parts = [str(m.get("content") or "").strip()]
            for call in m["tool_calls"]:
                fn = (call or {}).get("function") or {}
                parts.append(f"[called {fn.get('name')} with {fn.get('arguments')}]")
            out.append({"role": "assistant", "content": "\n".join(p for p in parts if p)})
            continue
        out.append(m)
    return out


def _attach_tool_contract(messages: list, tools: list) -> tuple[list, int]:
    """Append the tool contract to the last user turn. Returns (messages, n_tools_rendered)."""
    instruction, included = tool_instruction(tools)
    if not instruction:
        return messages, 0
    out = list(messages)
    for i in range(len(out) - 1, -1, -1):
        if isinstance(out[i], dict) and out[i].get("role") == "user":
            turn = dict(out[i])
            turn["content"] = str(turn.get("content") or "") + instruction
            out[i] = turn
            return out, included
    out.append({"role": "user", "content": instruction.strip()})
    return out, included


def _unwrap_no_tool_text(text: str) -> Optional[str]:
    """`{"tool": null, "text": "..."}` -> the text. Anything else -> None (leave the reply alone).

    The no-tool envelope is the shim's own protocol for "I read the tools and none applies". Shipping
    it verbatim hands the consumer our wire format as the model's words. Deliberately strict: only an
    object whose `tool` is EXACTLY null and whose `text` is a string is unwrapped, so a genuine JSON
    answer that happens to contain a "tool" key is never rewritten into something else.
    """
    if not text:
        return None
    blob = text.strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", blob).strip()
    if not blob.startswith("{"):
        return None
    try:
        obj = json.loads(blob)
    except ValueError:
        return None
    if not isinstance(obj, dict) or "tool" not in obj or obj.get("tool") is not None:
        return None
    body = obj.get("text")
    return body if isinstance(body, str) and body.strip() else None


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
        # Quarantine is operator data alongside the seat files.  SessionPool loads it at
        # construction, but the supported zero-restart rescan endpoint must also apply edits
        # to pool_quarantine.json; otherwise a newly quarantined broken adapter can still be
        # selected by the live auto router until an unsafe process restart.  Refresh the set
        # only after the seat rescan succeeds so a malformed quarantine file cannot disturb
        # the existing in-memory routing state.
        try:
            pool.quarantined = _load_quarantine()
        except Exception:
            pass
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
    attempts = []                                   # worklog #1137: never lose a failure reason
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
                        attempts=attempts, finished=time.time())
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
        # Record EVERY attempt's failure reason on the durable ledger (worklog #1137). The old
        # code overwrote `error` on each failover, so the akool/digen failure reasons in the
        # #1136 E2E were destroyed and undiagnosable. attempts[] keeps them all.
        attempts.append({"host": s.host, "session": s.key, "at": time.time(),
                         "error": last_err[:200]})
        JOBS.update(job_id, attempts=list(attempts))
    JOBS.update(job_id, status="failed", error=last_err[:300],
                attempts=attempts, finished=time.time())


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
            # Only list routes the router can actually dispatch RIGHT NOW.  Raw
            # session-file presence is not capacity: quarantined adapter defects
            # and dead/non-dispatchable seats must not be advertised to consumers.
            for s in pool.live():
                prefix = "video/" if s.modality == "video" else ""
                models.append({
                    "id": f"{prefix}{s.host}/auto",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "session_pool"
                })
            seat_ids = {m["id"] for m in models}
            upstream_models = omniroute.models()
            allowed_omni = _omni_verified_model_ids()
            for row in upstream_models:
                if allowed_omni is not None and str(row.get("id") or "") not in allowed_omni:
                    continue
                # A name collision belongs to the local seat route: it is the one
                # whose pin syntax the consumer explicitly requested.
                if row.get("id") not in seat_ids:
                    merged = dict(row)
                    merged.setdefault("owned_by", "omniroute")
                    merged["x_gateway_source"] = "omniroute"
                    models.append(merged)
            resp = {"object": "list", "data": models,
                    "x_gateway": {"seatPool": {"chat": len(pool.live("chat")),
                                                  "video": len(pool.live("video"))},
                                  "omniroute": omniroute.status()}}
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
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "request body must be valid JSON",
                                                   "type": "invalid_request_error",
                                                   "tenant": tenant}}).encode())
            return
            
        messages = req.get("messages", [])
        model = req.get("model", "")
        if not isinstance(messages, list) or not messages:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "messages must be a non-empty array",
                                                   "type": "invalid_request_error",
                                                   "tenant": tenant}}).encode())
            return
        host_target = None
        modality = "chat"
        seat_model = False
        
        if model and model.startswith("video/"):
            seat_model = True
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
            seat_model = True
            modality = "chat"
            host_target = model.split("/")[0]
            model = None
        elif model in ("auto", "auto/best-chat", "session-pool/auto", ""):
            seat_model = True
            modality = "chat"
            model = None

        # Non-seat model names are OmniRoute routes.  Keep their upstream reply
        # OpenAI-compatible, including its own model/tool details.  If OmniRoute is
        # unavailable, continue through the balanced session pool and say so in the
        # response; one sick paid service must never blank the consumer gateway.
        upstream_fallback = None
        if not seat_model:
            upstream_reply, upstream_fallback = omniroute.chat(
                body, self.headers.get("Authorization", ""))
            if upstream_reply is not None:
                upstream_reply["tenant"] = tenant
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(upstream_reply).encode())
                return
            # Once the Omni graduation ledger exists, a named Omni model that
            # is not in that exact-file/final-consumer allowlist must not fall
            # through to a session-pool answer.  Otherwise a caller could ask
            # for an ungraduated Omni route and receive a misleading healthy
            # response from a different harness.
            if upstream_fallback == "omniroute_route_not_admitted":
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "omniroute_route_not_admitted",
                    "message": "OmniRoute model has no fresh direct + :8190 consumer graduation proof",
                    "tenant": tenant}).encode())
                return
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

        # ------------------------------------------------------------- tools (worklog: :8190) ----
        # Consumers wired to this port were getting prose where they asked for a tool call, because
        # the tool shim existed only on :20130. Same contract now serves both faces.
        tools = _tools_from_request(req)
        send_messages = _flatten_tool_history(messages)
        tools_rendered = 0
        if tools:
            send_messages, tools_rendered = _attach_tool_contract(send_messages, tools)

        try:
            # Route based on detected modality. strict_json (worklog #1134, fix 1): JSON-intent
            # requests fail over any seat that answers prose/empty/fenced-JSON.
            result = pool.chat(send_messages, model=model, modality=modality, host=host_target,
                               # A tools request IS a strict-JSON request: the contract asks for one
                               # JSON object and nothing else. Enforcing it fails over any seat that
                               # answers prose (measured: api.monica.im replies "Omni." to a 44-tool
                               # contract) until a compliant seat answers. Shipping prose to a client
                               # that asked for a tool is the bug that cost weeks.
                               strict_json=_wants_strict_json(req) or bool(tools),
                               # ...but bounded. Unbounded, a tool request walks all 18 seats at a
                               # real round trip each and blew a 300s client timeout. Every rejected
                               # seat is also cooled down, so consecutive tool requests converge onto
                               # the seats that honour the contract instead of re-paying for the ones
                               # that do not.
                               tries=TOOL_FAILOVER_TRIES if tools else CHAT_FAILOVER_TRIES)
        except ChatError as e:
            # The merged gateway must remain useful when the free/session side is
            # temporarily exhausted.  Only unpinned auto routing may cross this
            # boundary: a caller who explicitly named a host asked us not to swap
            # providers.  Video never reaches here (it has its own durable path).
            if seat_model and host_target is None:
                # `session-pool/auto` is meaningful only to this gateway.  Passing
                # it upstream makes OmniRoute resolve an unrelated/stale alias on
                # some builds.  Use the documented paid-side fallback alias while
                # preserving every other request field verbatim.
                fallback_req = dict(req)
                fallback_req["model"] = OMNIROUTE_FALLBACK_MODEL
                upstream_reply, bridge_reason = omniroute.chat(
                    json.dumps(fallback_req).encode(), self.headers.get("Authorization", ""))
                if upstream_reply is not None:
                    upstream_reply["tenant"] = tenant
                    upstream_reply["x_gateway_source"] = "omniroute_fallback"
                    upstream_reply["x_gateway_fallback_reason"] = f"session_pool:{getattr(e, 'kind', 'chat_error')}"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(upstream_reply).encode())
                    return
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
            # Reaching here means the pool raised something that is NOT a ChatError, i.e. one of our
            # own adapters is broken rather than a provider refusing. Naming the type in the payload
            # matters: `ChatError.__init__() missing 1 required positional argument` reads like a
            # provider problem, and consumers spent a day treating a TypeError as an outage. The
            # traceback goes to stderr because str(e) alone gives no file or line.
            print(f"[shim] UNEXPECTED {type(e).__name__} on {self.path} -- returning 500:",
                  file=sys.stderr)
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {
                "message": f"{type(e).__name__}: {e}",
                "type": "internal_adapter_error",
                "hint": "a pool adapter raised a non-ChatError; see the shim's stderr for the "
                        "traceback. This is our bug, not the provider's.",
                "tenant": tenant}}).encode())
            return
            
        # ----------------------------------------------- render the reply, tool call or text ----
        text = result.get("text", "") or ""
        message = {"role": "assistant", "content": text}
        finish = "stop"
        if tools:
            if looks_like_overflow(text):
                # The seat answered with page markup instead of the contract. Failing closed is
                # deliberate: a client handed prose where it expected a tool call retries forever,
                # and that silent loop is exactly what made this class of bug cost weeks.
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {
                    "message": f"{result.get('provider')} returned {len(text)} bytes of page markup "
                               f"instead of the tool contract",
                    "type": "tool_contract_overflow", "tenant": tenant}}).encode())
                return
            name, tool_args, unresolved = parse_tool_call(text, tools)
            if unresolved and not name:
                # The seat invented a tool name that resolve_tool_name could not map to anything the
                # client registered. Reporting the invented string is the point -- guessing a name
                # here is how `No such tool available` became unfindable.
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {
                    "message": f"{result.get('provider')} named a tool that was never registered: "
                               f"{unresolved!r}",
                    "type": "tool_name_unresolved", "tenant": tenant}}).encode())
                return
            if name:
                message = {"role": "assistant", "content": None,
                           "tool_calls": [{"id": f"call_{int(time.time() * 1000)}",
                                           "type": "function",
                                           "function": {"name": name,
                                                        "arguments": json.dumps(tool_args or {})}}]}
                finish = "tool_calls"
            else:
                # The seat complied with the contract and declined to call a tool:
                # {"tool": null, "text": "..."}. parse_tool_call() correctly reports "no tool call",
                # but it discards the text, so without this the consumer receives the JSON ENVELOPE as
                # the assistant's message -- measured: chat.mistral.ai's refusal shipped verbatim as
                # `{"tool": null, "text": "I cannot execute shell commands..."}`. The envelope is OUR
                # protocol, not content; unwrap it. Gated on `tools` being present, so a plain request
                # that legitimately asks for JSON is never rewritten.
                unwrapped = _unwrap_no_tool_text(text)
                if unwrapped is not None:
                    message = {"role": "assistant", "content": unwrapped}

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
            # How many of the requested tools actually fitted under the prompt ceiling. Reported
            # because silent truncation reads as "all tools offered" when it was not.
            "x_pool_tools_rendered": f"{tools_rendered}/{len(tools)}" if tools else None,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        if upstream_fallback:
            resp["x_gateway_source"] = "session_pool_fallback"
            resp["x_gateway_fallback_reason"] = upstream_fallback
        
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
