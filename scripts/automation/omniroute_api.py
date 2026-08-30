#!/usr/bin/env python3
"""
Shared OmniRoute management/inference API client for the Monetizer automation.

Design rules (from AGENTS.md):
- NEVER restart/stop/kill the OmniRoute service; only supported /api calls.
- NEVER log secrets (keys, tokens, passwords, cookies). All logging is redacted.
- Idempotent: repeated runs converge, never destroy healthy state.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Import ModelCatalogCache for /v1/models performance optimization
try:
    from model_cache import ModelCatalogCache
except ImportError:
    # Fallback if model_cache not available
    ModelCatalogCache = None

_raw_base = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if _raw_base.endswith("/v1"):
    _raw_base = _raw_base[:-3].rstrip("/")
BASE_URL = _raw_base or "http://localhost:20128"
API_URL = f"{BASE_URL}/api"
V1_URL = f"{BASE_URL}/v1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Initialize global model catalog cache (TTL 60s, disk persistence)
_model_cache = None
if ModelCatalogCache:
    _model_cache = ModelCatalogCache(ttl_seconds=60, cache_file=STATE_DIR / "model_cache.json")

SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|gh[opsu]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
    r"key-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9_\-\.]{16,})",
    re.I,
)

# Media providers return *presigned* asset URLs whose query string carries real
# credential material — Alibaba OSS embeds `OSSAccessKeyId` and `Signature`, GCS and S3
# embed their own equivalents. These match none of the patterns above, so a video URL
# logged verbatim would leak an access key id. Strip the query string instead: the path
# is what identifies the asset, and the signature is never worth persisting.
PRESIGN_PARAM_RE = re.compile(
    r"[?&](?:OSSAccessKeyId|Signature|X-Amz-Signature|X-Amz-Credential|X-Goog-Signature|"
    r"X-Goog-Credential|AWSAccessKeyId|sig|token|se|sp|sv|st)=",
    re.I,
)

# Management login is bcrypt-bound and measured at ~9.5s on this host, so the previous
# 15s ceiling left only ~5s of headroom and raised ReadTimeout intermittently across
# every management script in the repo. Widened deliberately: a slow login is normal,
# a failed one is not.
LOGIN_TIMEOUT = int(os.environ.get("OMNIROUTE_LOGIN_TIMEOUT", "120"))


def redact(value: Any) -> str:
    """Redact anything that looks like a secret in a string."""
    s = str(value)
    return SECRET_RE.sub("[REDACTED]", s)


def redact_url(url: str) -> str:
    """Drop the query string from a presigned asset URL, keeping it identifiable.

    Applied to media URLs before they are logged or persisted. See PRESIGN_PARAM_RE:
    the signature params are credential material, and the URL is short-lived anyway,
    so the durable value is the object path, not the grant.
    """
    s = str(url)
    if "?" in s and PRESIGN_PARAM_RE.search(s):
        return s.split("?", 1)[0] + "?[PRESIGN_REDACTED]"
    return redact(s)


def mask_token(token: str) -> str:
    if not token:
        return "<empty>"
    if len(token) <= 10:
        return "[REDACTED]"
    return f"{token[:6]}...{token[-4:]}"


def log(msg: str, level: str = "info") -> None:
    prefix = {"info": "[*]", "ok": "[+]", "warn": "[!]", "err": "[-]", "skip": "[~]"}.get(level, "[*]")
    print(f"{prefix} {redact(msg)}", flush=True)


def get_password() -> str:
    """Management password: env var first, then Windows DPAPI vault (T11-compliant).

    Never hard-coded. The vault (state/omniroute_password.bin) is encrypted with
    CryptProtectData and only decryptable by the same Windows user.
    """
    env = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
    if env:
        return env
    try:
        import importlib.util
        vault_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "password_vault.py")
        spec = importlib.util.spec_from_file_location("password_vault", vault_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.retrieve_password().strip()
    except Exception:
        return ""


def get_api_key() -> str:
    """Optional inference bearer key from environment only."""
    return os.environ.get("OMNIROUTE_API_KEY", "").strip()


def extract_chat_content(body: Any, raw_text: str = "") -> str:
    """Extract visible assistant text from JSON or OpenAI-compatible SSE replies.

    Some upstreams emit `text/event-stream` even when a client requests a
    non-streaming completion.  A 200 response with a valid SSE answer is a
    successful inference, not a failed JSON parse.
    """
    def from_payload(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice = choices[0]
            message = choice.get("message") or choice.get("delta") or {}
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
        output_text = payload.get("output_text")
        return output_text if isinstance(output_text, str) else ""

    content = from_payload(body)
    if content or not raw_text:
        return content
    # Some OmniRoute upstreams emit cumulative SSE fragments ("5", then "58")
    # while others emit deltas ("5", then "8").  Joining both naively turns the
    # former into "558" or, for repeated terminal frames, "5858".  Keep the
    # longest cumulative extension, but retain genuine one-character repeated
    # deltas ("a", "a" -> "aa").
    chunks: list[str] = []
    for line in raw_text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            piece = from_payload(json.loads(data))
        except (TypeError, ValueError):
            continue
        if piece:
            chunks.append(piece)
    accumulated = ""
    for piece in chunks:
        if accumulated and piece.startswith(accumulated) and len(piece) > len(accumulated):
            accumulated = piece
        elif accumulated and piece == accumulated and len(accumulated) >= 2:
            continue
        else:
            accumulated += piece
    return accumulated


class OmniRouteAPI:
    """Session-based client for the OmniRoute management + inference APIs."""

    def __init__(self, base_url: str = BASE_URL, password: Optional[str] = None):
        self.base = base_url.rstrip("/")
        if self.base.endswith("/v1"):
            self.base = self.base[:-3].rstrip("/")
        self.api = f"{self.base}/api"
        self.v1 = f"{self.base}/v1"
        self.session = requests.Session()
        self._password = password if password is not None else get_password()
        self._logged_in = False

    # ------------------------------------------------------------------ auth
    def login(self) -> bool:
        if not self._password:
            log("OMNIROUTE_PASSWORD not set; management calls will be skipped", "warn")
            return False
        r = self.session.post(
            f"{self.api}/auth/login",
            json={"password": self._password},
            timeout=LOGIN_TIMEOUT,
        )
        if r.status_code != 200:
            log(f"Management login failed: HTTP {r.status_code}", "err")
            return False
        token = self.session.cookies.get("auth_token")
        if not token:
            try:
                body = r.json()
                token = body.get("token") or body.get("auth_token") or body.get("access_token")
                if token:
                    self.session.cookies.set("auth_token", token)
            except Exception:
                pass
        self._logged_in = True
        log("Management login OK", "ok")
        return True

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    def _ensure_login(self) -> None:
        if not self._logged_in:
            if not self.login():
                raise RuntimeError("Not authenticated to OmniRoute management API")

    # ------------------------------------------------------------- providers
    def get_connections(self) -> List[Dict[str, Any]]:
        self._ensure_login()
        r = self.session.get(f"{self.api}/providers", timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("connections", []) if isinstance(data, dict) else []

    def update_connection(self, cid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /api/providers/{id} with a partial patch (e.g. apiKey, isActive)."""
        self._ensure_login()
        r = self.session.put(f"{self.api}/providers/{cid}", json=patch, timeout=20)
        try:
            body = r.json()
        except Exception:
            body = {"raw": redact(r.text[:500])}
        return {"http_status": r.status_code, "body": body}

    def create_connection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/providers to add a NEW provider connection.

        There was no create path in this client before 2026-08-23 -- every provider we touched
        already existed. Google Flow is the first genuinely new video connection: its `google-flow`
        format is in OmniRoute's registry but no connection instance existed, so one has to be
        created. The management route that backs the dashboard's "Add provider" button is
        POST /api/providers; the body mirrors the fields a GET connection returns (provider,
        apiKey, authType, name, isActive, priority). The token goes in `apiKey` exactly as the
        vertex connection stores its harvested Google OAuth token (measured: vertex.apiKey begins
        `AQ.` -- a Google token, not a GCP key), so google-flow follows the same convention.

        Returns {http_status, body}. Never logs the token: the caller masks it.
        """
        self._ensure_login()
        r = self.session.post(f"{self.api}/providers", json=payload, timeout=30)
        try:
            body = r.json()
        except Exception:
            body = {"raw": redact(r.text[:500])}
        return {"http_status": r.status_code, "body": body}

    def test_connection(self, cid: str) -> Dict[str, Any]:
        self._ensure_login()
        try:
            r = self.session.post(f"{self.api}/providers/{cid}/test", timeout=45)
            try:
                body = r.json()
            except Exception:
                body = {"raw": redact(r.text[:500])}
            return {"http_status": r.status_code, "result": body}
        except Exception as e:
            return {"http_status": None, "result": {"valid": False, "error": f"{type(e).__name__}: {e}"}}

    def connection_models(self, cid: str) -> List[str]:
        """The model ids OmniRoute will actually route for ONE connection.

        MEASURED 2026-08-23: `/v1/models` listed 7469 ids across 118 prefixes and yet contained
        NO first-party `reka/` entry, while `POST /v1/chat/completions` on `reka/reka-flash-3`
        returned 200 with real streamed text and the dashboard's own tester reported
        "reka-edge-2603 is working, 1412ms". So the aggregate list is not a precondition for
        routing, and gating a provider's proof on it produced a false negative that deleted a
        working row twice. This endpoint is what the dashboard itself reads.
        """
        self._ensure_login()
        try:
            r = self.session.get(f"{self.api}/providers/{cid}/models", timeout=45)
            if r.status_code != 200:
                return []
            return [str(m.get("id")) for m in (r.json().get("models") or []) if m.get("id")]
        except Exception:
            return []

    def refresh_connection(self, cid: str) -> Dict[str, Any]:
        self._ensure_login()
        try:
            r = self.session.post(f"{self.api}/providers/{cid}/refresh", timeout=60)
            try:
                body = r.json()
            except Exception:
                body = {"raw": redact(r.text[:500])}
            return {"http_status": r.status_code, "result": body}
        except Exception as e:
            return {"http_status": None, "result": {"error": f"{type(e).__name__}: {e}"}}

    # ---------------------------------------------------------------- combos
    def get_combos(self) -> List[Dict[str, Any]]:
        self._ensure_login()
        r = self.session.get(f"{self.api}/combos", timeout=60)
        r.raise_for_status()
        data = r.json()
        return data.get("combos", []) if isinstance(data, dict) else []

    def update_combo(self, combo_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /api/combos/{id}. Invalidate model cache after update."""
        self._ensure_login()
        r = self.session.put(f"{self.api}/combos/{combo_id}", json=payload, timeout=60)
        
        # Invalidate model cache if combo update succeeds (models may have changed)
        if r.status_code == 200 and _model_cache:
            _model_cache.invalidate()
            log(f"Model cache invalidated after combo update", "ok")
        
        try:
            body = r.json()
        except Exception:
            body = {"raw": redact(r.text[:500])}
        return {"http_status": r.status_code, "body": body}

    # ------------------------------------------------------------- inference
    def list_models(self) -> List[Dict[str, Any]]:
        """Get model catalog, with TTL caching to avoid 30-60s rebuilds."""
        # Use cache if available to reduce latency from 30-60s to <100ms
        if _model_cache:
            try:
                def fetch_fresh():
                    headers = {}
                    key = get_api_key()
                    if key:
                        headers["Authorization"] = f"Bearer {key}"
                    r = requests.get(f"{self.v1}/models", headers=headers, timeout=120)
                    r.raise_for_status()
                    data = r.json()
                    return data.get("data", []) if isinstance(data, dict) else []
                
                models = _model_cache.get_models(fetch_fn=fetch_fresh)
                if models:
                    return models
            except Exception as e:
                log(f"Cache fetch failed, falling back to direct: {e}", "warn")
        
        # Fallback: direct fetch without cache
        headers = {}
        key = get_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        # /v1/models returns the full catalog (~2.5k models) and can take 30-60s
        r = requests.get(f"{self.v1}/models", headers=headers, timeout=120)
        r.raise_for_status()
        data = r.json()
        return data.get("data", []) if isinstance(data, dict) else []

    def chat_probe(self, model: str, timeout: int = 30) -> Dict[str, Any]:
        """Minimal but VALID chat completion probe (per AGENTS.md: no tiny payloads)."""
        headers = {"Content-Type": "application/json"}
        key = get_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Reply with the single word: OK"}
            ],
            "max_tokens": 16,
            "temperature": 0,
            "stream": False,
        }
        start = time.monotonic()
        try:
            r = requests.post(
                f"{self.v1}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            elapsed = round(time.monotonic() - start, 3)
            raw_text = r.text if r.status_code == 200 else ""
            try:
                body = r.json()
            except Exception:
                body = {"raw": redact(raw_text[:500])}
            content = extract_chat_content(body, raw_text) if r.status_code == 200 else ""
            return {
                "model": model,
                "http_status": r.status_code,
                "latency": elapsed,
                "ok": r.status_code == 200 and bool(content),
                "response_model": body.get("model") if isinstance(body, dict) else None,
                "content_preview": content[:80],
                "error": None if r.status_code == 200 else redact(str(body))[:300],
            }
        except Exception as e:
            return {
                "model": model,
                "http_status": None,
                "latency": round(time.monotonic() - start, 3),
                "ok": False,
                "response_model": None,
                "content_preview": "",
                "error": f"{type(e).__name__}: {e}",
            }


def save_json(name: str, data: Any, subdir: Optional[str] = None) -> Path:
    target_dir = STATE_DIR / subdir if subdir else STATE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
