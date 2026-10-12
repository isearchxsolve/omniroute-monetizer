#!/usr/bin/env python3
"""
Kaggle Integration Module — Wires Kaggle Pool Gateway into OmniRoute Architecture

This module integrates the Kaggle account rotation gateway with the existing
chat_pool_server (port 20130) and session_pool (port 8190) architecture.

Integration Strategy:
1. Kaggle Gateway runs on port 20135 (stable endpoint with 5-account rotation)
2. chat_pool_server treats Kaggle as a secondary upstream (after :20128 paid)
3. session_pool can dispatch to Kaggle via HTTP gateway
4. Models exposed as `kaggle/*` and `pool/kaggle-*` for selection
"""
from __future__ import annotations
import json
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional

# Import existing components
from chat_pool_server import Pool, Provider, Upstream, Handler, claude_alias, log
from kaggle_pool_gateway import get_kaggle_gateway, KagglePoolGateway

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Kaggle gateway configuration
KAGGLE_GATEWAY_PORT = 20135
KAGGLE_GATEWAY_BASE = f"http://127.0.0.1:{KAGGLE_GATEWAY_PORT}"

# Global gateway instance
_kaggle_gateway: Optional[KagglePoolGateway] = None
_kaggle_upstream: Optional[Upstream] = None
_gateway_lock = threading.Lock()


def start_kaggle_integration() -> KagglePoolGateway:
    """Start the Kaggle gateway and return the instance."""
    global _kaggle_gateway
    with _gateway_lock:
        if _kaggle_gateway is None:
            _kaggle_gateway = get_kaggle_gateway(KAGGLE_GATEWAY_PORT)
            _kaggle_gateway.start()
            log(f"[KaggleIntegration] Gateway started on {KAGGLE_GATEWAY_BASE}")
        return _kaggle_gateway


def stop_kaggle_integration() -> None:
    """Stop the Kaggle gateway."""
    global _kaggle_gateway
    with _gateway_lock:
        if _kaggle_gateway:
            _kaggle_gateway.stop()
            _kaggle_gateway = None
            log("[KaggleIntegration] Gateway stopped")


def get_kaggle_upstream() -> Upstream:
    """Get or create the Kaggle upstream for chat_pool_server."""
    global _kaggle_upstream
    if _kaggle_upstream is None:
        _kaggle_upstream = Upstream(KAGGLE_GATEWAY_BASE, key="")
    return _kaggle_upstream


class KaggleUpstream:
    """
    Kaggle gateway as an upstream for chat_pool_server.
    
    This sits alongside the OmniRoute upstream (:20128). Requests that
    are not pool/* and fail on :20128 will fall back to Kaggle gateway.
    """
    
    def __init__(self, base: str = KAGGLE_GATEWAY_BASE):
        self.base = base.rstrip("/")
        self.calls = 0
        self.ok = 0
        self.fallbacks = 0
        self.last_reason = ""
        self._gateway = start_kaggle_integration()
    
    def forward(self, path: str, raw: bytes, auth: str = "") -> tuple:
        """Forward request to Kaggle gateway. Returns (status, text, ctype, fallback_reason)."""
        import requests
        
        hdrs = {"content-type": "application/json"}
        if auth:
            hdrs["authorization"] = auth
        
        self.calls += 1
        
        try:
            r = requests.post(f"{self.base}{path}", data=raw, headers=hdrs, timeout=120)
        except Exception as e:
            self.last_reason = f"kaggle gateway {self.base} unreachable: {type(e).__name__}"
            self.fallbacks += 1
            return None, "", "", self.last_reason
        
        text = r.text or ""
        ctype = r.headers.get("content-type", "application/json")
        low = text.lower()
        
        if r.status_code >= 400:
            self.last_reason = f"kaggle gateway HTTP {r.status_code}"
            self.fallbacks += 1
            return r.status_code, text, ctype, self.last_reason
        
        # Check for error envelope
        if '"error"' in low:
            self.last_reason = f"kaggle gateway returned 200 with error envelope"
            self.fallbacks += 1
            return r.status_code, text, ctype, self.last_reason
        
        self.ok += 1
        return r.status_code, text, ctype, ""
    
    def models(self) -> List[Dict]:
        """Get models from Kaggle gateway."""
        import requests
        try:
            r = requests.get(f"{self.base}/v1/models", timeout=6)
            d = r.json()
            rows = d.get("data") if isinstance(d, dict) else None
            # Transform to include source=kaggle
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        row["source"] = "kaggle"
            return rows if isinstance(rows, list) else []
        except Exception:
            return []
    
    def status(self) -> Dict[str, Any]:
        gateway_health = self._gateway.handle_health() if self._gateway else {}
        return {
            "base": self.base,
            "role": "Kaggle 5-account rotation gateway (fallback after :20128)",
            "calls": self.calls,
            "ok": self.ok,
            "fellBackToPool": self.fallbacks,
            "lastFallbackReason": self.last_reason or None,
            "gateway_health": gateway_health,
        }


def patch_chat_pool_server_for_kaggle(server_handler_class: type) -> type:
    """
    Patch the chat_pool_server Handler to include Kaggle as a secondary upstream.
    
    This creates a new handler class that:
    1. First tries OmniRoute upstream (:20128) for non-pool/* models
    2. Then tries Kaggle gateway (:20135) if OmniRoute falls back
    3. Finally falls back to local pool if both upstreams fail
    """
    original_do_post = server_handler_class.do_POST
    
    def patched_do_post(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in ("/v1/messages", "/v1/chat/completions"):
            return original_do_post(self)
        
        body = self._read_json()
        if body is None:
            self._err(400, "invalid_request_error", "body is not JSON")
            return
        
        model = str(body.get("model") or "")
        
        # If model explicitly starts with kaggle/, route directly to Kaggle gateway
        if model.startswith("kaggle/"):
            self._forward_to_kaggle(path, body, model)
            return
        
        # If model is pool/kaggle-*, treat as pool selection
        if model.startswith("pool/kaggle-"):
            # Let the pool handle it (will need Kaggle providers in pool)
            return original_do_post(self)
        
        # For all other models: OmniRoute first, then Kaggle, then pool
        fb_kaggle = ""
        
        # 1. Try OmniRoute upstream (existing behavior)
        if self.upstream and not model.startswith("pool/"):
            code, text, ctype, fb = self.upstream.forward(
                path, self._raw, self.headers.get("Authorization") or "")
            if not fb:
                log(f"  upstream {model or '(default)':26s} OK   HTTP {code}")
                self._send_raw(code, text, ctype)
                return
            log(f"  upstream {model or '(default)':26s} -> kaggle: {fb}")
        
        # 2. Try Kaggle gateway
        kaggle_upstream = get_kaggle_upstream()
        if not model.startswith("pool/"):
            code, text, ctype, fb_kaggle = kaggle_upstream.forward(path, self._raw, 
                                                                     self.headers.get("Authorization") or "")
            if not fb_kaggle:
                log(f"  kaggle gateway {model or '(default)':26s} OK   HTTP {code}")
                self._send_raw(code, text, ctype)
                return
            log(f"  kaggle gateway {model or '(default)':26s} -> pool: {fb_kaggle}")
        
        # 3. Fall back to local pool (existing behavior)
        # Combine fallback reasons
        fb_combined = fb_kaggle
        if self.upstream and hasattr(self.upstream, 'last_reason') and self.upstream.last_reason:
            fb_combined = f"omniroute: {self.upstream.last_reason}; kaggle: {fb_kaggle}"
        
        # Continue with pool dispatch
        messages = to_messages(body)
        if not messages:
            self._err(400, "invalid_request_error", "no messages in request")
            return
        prompt = as_single_prompt(messages)
        anthropic = path == "/v1/messages"
        
        tools = body.get("tools") if isinstance(body.get("tools"), list) else []
        tool_text, n_tools = tool_instruction(tools) if tools else ("", 0)
        if tools:
            if n_tools < len(tools):
                log(f"  tools: rendered {n_tools}/{len(tools)} into the prompt "
                    f"(ceiling {TOOL_PROMPT_CEILING}B) -- the rest were dropped")
            prompt = prompt + tool_text
        
        text, used, detail = self._dispatch(prompt, body.get("model"))
        if text is None:
            if fb_combined:
                detail = f"upstreams fell back ({fb_combined}) and the pool could not cover it: {detail}"
            self._err(503, "overloaded_error", detail)
            return
        
        unwrapped = unwrap_no_tool_text(text)
        if unwrapped is not None:
            text = unwrapped
        
        if looks_like_overflow(text):
            log(f"  {used}: reply looks like page chrome, not an answer -- seat overflowed")
            self._err(502, "api_error",
                      f"pool seat {used} returned page HTML rather than a reply")
            return
        
        tool_name, tool_args, unresolved = (parse_tool_call(text, tools) if tools else (None, {}, None))
        if unresolved:
            log(f"  {used}: named a tool that was not offered: {unresolved!r}")
            self._err(502, "api_error",
                      f"pool seat {used} asked to call {unresolved!r}")
            return
        
        # Build response (same as original)
        if anthropic:
            if tool_name:
                content = [{"type": "tool_use", "id": f"toolu_{uuid.uuid4().hex[:24]}",
                            "name": tool_name, "input": tool_args}]
                log(f"  {used}: tool_use {tool_name}")
            else:
                content = [{"type": "text", "text": text}]
            out = {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": body.get("model") or f"pool/{used}",
                "content": content,
                "stop_reason": "tool_use" if tool_name else "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": approx_tokens(prompt),
                          "output_tokens": approx_tokens(text)},
                "x_pool_provider": used,
            }
        else:
            msg: dict[str, Any] = {"role": "assistant", "content": None if tool_name else text}
            if tool_name:
                msg["tool_calls"] = [{"id": f"call_{uuid.uuid4().hex[:20]}", "type": "function",
                                      "function": {"name": tool_name,
                                                   "arguments": json.dumps(tool_args)}}]
            out = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:20]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model") or f"pool/{used}",
                "choices": [{"index": 0,
                             "finish_reason": "tool_calls" if tool_name else "stop",
                             "message": msg}],
                "usage": {"prompt_tokens": approx_tokens(prompt),
                          "completion_tokens": approx_tokens(text),
                          "total_tokens": approx_tokens(prompt) + approx_tokens(text)},
                "x_pool_provider": used,
            }
        if tools:
            out["x_pool_tools_rendered"] = f"{n_tools}/{len(tools)}"
        if fb_combined:
            out["x_pool_fallback_reason"] = fb_combined
        self._send(200, out)
    
    def _forward_to_kaggle(self, path: str, body: Dict, model: str) -> None:
        """Forward request directly to Kaggle gateway for kaggle/* models."""
        kaggle_upstream = get_kaggle_upstream()
        
        # Rewrite model to strip kaggle/ prefix
        if model.startswith("kaggle/"):
            body = dict(body)
            body["model"] = model[7:]  # Remove "kaggle/" prefix
        
        raw = json.dumps(body).encode("utf-8")
        code, text, ctype, fb = kaggle_upstream.forward(
            path, raw, self.headers.get("Authorization") or "")
        
        if fb:
            self._err(502, "api_error", f"Kaggle gateway failed: {fb}")
            return
        
        self._send_raw(code, text, ctype)
    
    # Import needed functions
    from chat_pool_server import (
        to_messages, as_single_prompt, tool_instruction, TOOL_PROMPT_CEILING,
        unwrap_no_tool_text, looks_like_overflow, parse_tool_call, approx_tokens
    )
    import uuid
    
    # Replace do_POST
    server_handler_class.do_POST = patched_do_post
    
    # Also patch do_GET for /v1/models to include Kaggle models
    original_do_get = server_handler_class.do_GET
    
    def patched_do_get(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/v1/models":
            # Get pool models (original)
            mine, seen = [], set()
            for p in self.pool.providers:
                mid = claude_alias(p.name)
                if mid in seen:
                    mid = f"pool/claude-sonnet-4-6-{p.name}"
                seen.add(mid)
                mine.append({"id": mid, "object": "model", "owned_by": p.host,
                             "source": "pool", "state": p.status()["state"],
                             "x_host_id": f"pool/{p.name}"})
            mine.insert(0, {"id": "pool/claude-sonnet-4-6", "object": "model", "owned_by": "pool",
                            "source": "pool", "state": "rotates over every healthy provider",
                            "x_host_id": "pool/auto"})
            
            # Get upstream models (OmniRoute)
            up = []
            if self.upstream:
                for row in self.upstream.models():
                    if isinstance(row, dict) and row.get("id"):
                        r = dict(row)
                        r["source"] = "upstream"
                        up.append(r)
            
            # Get Kaggle models
            kaggle_models = []
            kaggle_upstream = get_kaggle_upstream()
            for row in kaggle_upstream.models():
                if isinstance(row, dict) and row.get("id"):
                    r = dict(row)
                    # Prefix with kaggle/ for direct routing
                    if not r["id"].startswith("kaggle/"):
                        r["id"] = f"kaggle/{r['id']}"
                    r["source"] = "kaggle"
                    kaggle_models.append(r)
            
            # Also add pool/kaggle-* aliases for pool-style selection
            for row in kaggle_models:
                pool_alias = row["id"].replace("kaggle/", "pool/kaggle-")
                kaggle_models.append({
                    **row,
                    "id": pool_alias,
                    "x_host_id": pool_alias,
                })
            
            # Upstream first, then Kaggle, then pool
            self._send(200, {"object": "list", "data": up + kaggle_models + mine,
                             "x_upstream_reachable": bool(up) if self.upstream else None,
                             "x_kaggle_reachable": bool(kaggle_models)})
        else:
            return original_do_get(self)
    
    server_handler_class.do_GET = patched_do_get
    
    return server_handler_class


def add_kaggle_providers_to_pool(pool: Pool) -> None:
    """
    Add Kaggle gateway as virtual providers to the Pool.
    
    This allows the pool's LRU dispatcher to route to Kaggle accounts
    alongside captured browser sessions.
    """
    gateway = start_kaggle_integration()
    healthy_accounts = gateway.manager.get_healthy_accounts()
    
    for acc in healthy_accounts:
        # Create a virtual provider for each healthy Kaggle account
        from chat_pool_server import slug
        
        class KaggleVirtualProvider(Provider):
            def __init__(self, account: KaggleAccount):
                # Create a minimal session file path (virtual)
                virtual_path = pathlib.Path(f"virtual://kaggle/{account.account_id}")
                super().__init__(virtual_path, f"kaggle-{account.account_id}", "KAGGLE_GATEWAY")
                self.account = account
                self.name = f"kaggle-{account.account_id}"
            
            def client(self):
                # Return a client that calls the Kaggle gateway
                from kaggle_pool_gateway import KaggleSession
                if self.account.account_id not in gateway.sessions:
                    gateway.sessions[self.account.account_id] = KaggleSession(account=self.account)
                return gateway.sessions[self.account.account_id]
        
        # Check if already added
        existing = next((p for p in pool.providers if p.name == f"kaggle-{acc.account_id}"), None)
        if not existing:
            pool.providers.append(KaggleVirtualProvider(acc))
            log(f"[KaggleIntegration] Added virtual provider: kaggle-{acc.account_id}")


# Health check endpoint for monitoring
def get_kaggle_integration_status() -> Dict[str, Any]:
    """Get comprehensive status of Kaggle integration."""
    gateway = get_kaggle_gateway(KAGGLE_GATEWAY_PORT) if _kaggle_gateway else None
    
    return {
        "gateway": {
            "running": _kaggle_gateway is not None,
            "port": KAGGLE_GATEWAY_PORT,
            "base_url": KAGGLE_GATEWAY_BASE,
            "health": gateway.handle_health() if gateway else None,
        },
        "upstream": get_kaggle_upstream().status() if _kaggle_gateway else None,
        "integration": {
            "chat_pool_patched": True,
            "models_exposed": ["kaggle/*", "pool/kaggle-*"],
            "fallback_order": ["omniroute (:20128)", "kaggle_gateway (:20135)", "local_pool"],
        }
    }


if __name__ == "__main__":
    # Test the integration
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Starting Kaggle integration test...")
        gateway = start_kaggle_integration()
        time.sleep(2)
        
        status = get_kaggle_integration_status()
        print(json.dumps(status, indent=2, default=str))
        
        # Test a request
        import requests
        resp = requests.post(
            f"{KAGGLE_GATEWAY_BASE}/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Say hello"}]},
            timeout=60
        )
        print(f"\nTest response: {resp.status_code}")
        print(resp.json())
        
        stop_kaggle_integration()
    else:
        print("Usage: python kaggle_integration.py test")