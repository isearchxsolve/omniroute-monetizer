#!/usr/bin/env python3
"""
Kaggle Pool Gateway — Stable Endpoint with Seamless Account Handoff

This gateway presents a single stable HTTP endpoint (e.g., /v1/chat/completions)
that internally routes to the current active Kaggle account. When rotation occurs,
requests seamlessly fail over to the next healthy account without client disruption.

Architecture:
- Wraps the existing session_pool / chat_pool_server patterns
- Uses curl_cffi with Chrome TLS impersonation for Kaggle API calls
- Maintains per-account session cookies
- Transparent failover with request retry on rotation boundaries
"""
from __future__ import annotations
import json
import pathlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
    _HAVE_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    _HAVE_CURL_CFFI = False

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from kaggle_account_manager import get_kaggle_manager, KaggleAccount, AccountStatus

DEFAULT_PORT = 20135
KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"

# Kaggle-specific models we expose
KAGGLE_MODELS = [
    "kaggle/gpt-4o-mini",
    "kaggle/gpt-4o",
    "kaggle/claude-3.5-sonnet",
    "kaggle/gemini-1.5-pro",
    "kaggle/llama-3.1-405b",
    "kaggle/llama-3.1-70b",
    "kaggle/mixtral-8x7b",
]


@dataclass
class KaggleSession:
    """Holds the authenticated session for a Kaggle account."""
    account: KaggleAccount
    session_cookie: str = ""
    user_agent: str = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36")
    csrf_token: str = ""
    last_used: float = 0.0
    request_count: int = 0
    
    def headers(self) -> Dict[str, str]:
        h = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Origin": "https://www.kaggle.com",
            "Referer": "https://www.kaggle.com/",
        }
        if self.session_cookie:
            h["Cookie"] = self.session_cookie
        if self.csrf_token:
            h["X-CSRF-Token"] = self.csrf_token
        return h


class KagglePoolGateway:
    """
    Stable gateway endpoint that routes to active Kaggle accounts.
    Provides OpenAI-compatible /v1/chat/completions and /v1/models.
    """
    
    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.manager = get_kaggle_manager()
        self.sessions: Dict[str, KaggleSession] = {}
        self._lock = threading.RLock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._request_count = 0
        self._start_time = time.time()
        
        # Start the account rotation manager
        self.manager.start_rotation()
        # Give it a moment to initialize
        time.sleep(1.0)
        self._sync_sessions()
    
    def _sync_sessions(self) -> None:
        """Sync local sessions with manager's active accounts."""
        with self._lock:
            active_accounts = self.manager.get_active_accounts()
            active_ids = {a.account_id for a in active_accounts}
            
            # Remove sessions for inactive accounts
            to_remove = [k for k in self.sessions if k not in active_ids]
            for k in to_remove:
                del self.sessions[k]
            
            # Create sessions for new active accounts
            for acc in active_accounts:
                if acc.account_id not in self.sessions:
                    self.sessions[acc.account_id] = KaggleSession(account=acc)
                    # TODO: Load actual session cookie from credential store
                    self._load_session_cookies(acc.account_id)
    
    def _load_session_cookies(self, account_id: str) -> None:
        """Load session cookies from Windows Credential Manager or env vars."""
        # TODO: Implement actual cookie loading
        # For now, placeholder - operator must populate
        pass
    
    def get_best_session(self) -> Optional[KaggleSession]:
        """Get the best available session for a new request."""
        with self._lock:
            self._sync_sessions()
            
            best_acc = self.manager.get_best_account()
            if not best_acc or best_acc.account_id not in self.sessions:
                return None
            
            session = self.sessions[best_acc.account_id]
            session.last_used = time.time()
            session.request_count += 1
            return session
    
    def _make_kaggle_request(self, session: KaggleSession, 
                             messages: List[Dict], model: str,
                             stream: bool = False) -> Tuple[Optional[Dict], Optional[str]]:
        """Make a request to Kaggle's API via the session."""
        url = f"{KAGGLE_API_BASE}/chat/completions"
        
        # Map our model names to Kaggle's
        kaggle_model = self._map_model(model)
        
        payload = {
            "model": kaggle_model,
            "messages": messages,
            "stream": stream,
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        
        headers = session.headers()
        
        try:
            if _HAVE_CURL_CFFI:
                resp = curl_requests.post(
                    url, 
                    json=payload, 
                    headers=headers,
                    impersonate="chrome",
                    timeout=120,
                    stream=stream
                )
            else:
                resp = curl_requests.post(
                    url, 
                    json=payload, 
                    headers=headers,
                    timeout=120,
                    stream=stream
                )
            
            if resp.status_code == 401 or resp.status_code == 403:
                # Session expired - mark account for rotation
                self.manager.record_request(session.account.account_id, success=False)
                return None, f"AUTH_FAILED_{resp.status_code}"
            
            if resp.status_code == 429:
                return None, "RATE_LIMITED"
            
            if resp.status_code != 200:
                return None, f"HTTP_{resp.status_code}: {resp.text[:200]}"
            
            if stream:
                # Return streaming response handler
                return {"stream": resp}, None
            
            data = resp.json()
            self.manager.record_request(session.account.account_id, success=True)
            return data, None
            
        except Exception as e:
            self.manager.record_request(session.account.account_id, success=False)
            return None, f"REQUEST_ERROR: {e}"
    
    def _map_model(self, model: str) -> str:
        """Map gateway model names to Kaggle's internal names."""
        # Strip kaggle/ prefix if present
        if model.startswith("kaggle/"):
            model = model[7:]
        return model
    
    def _format_openai_response(self, data: Dict, model: str) -> Dict:
        """Format Kaggle response to OpenAI-compatible format."""
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": data.get("choices", [{}])[0].get("message", {}).get("content", "")
                },
                "finish_reason": "stop"
            }],
            "usage": data.get("usage", {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            })
        }
    
    def handle_chat_completions(self, body: Dict) -> Tuple[Dict, int]:
        """Handle /v1/chat/completions request with failover."""
        messages = body.get("messages", [])
        model = body.get("model", "kaggle/gpt-4o-mini")
        stream = body.get("stream", False)
        
        if not messages:
            return {"error": "messages required"}, 400
        
        # Try up to 3 different accounts
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            session = self.get_best_session()
            if not session:
                return {"error": "No healthy Kaggle accounts available"}, 503
            
            data, error = self._make_kaggle_request(session, messages, model, stream)
            
            if error is None:
                if stream:
                    # TODO: Implement streaming response
                    return {"error": "Streaming not yet implemented"}, 501
                return self._format_openai_response(data, model), 200
            
            last_error = error
            
            # If auth failed, force sync and try next account
            if "AUTH_FAILED" in error:
                with self._lock:
                    if session.account_id in self.sessions:
                        del self.sessions[session.account_id]
                continue
            
            # For other errors, try next account
            continue
        
        return {"error": f"All accounts failed: {last_error}"}, 502
    
    def handle_models(self) -> Dict:
        """Handle /v1/models - return available models."""
        return {
            "object": "list",
            "data": [
                {"id": m, "object": "model", "owned_by": "kaggle", "permission": []}
                for m in KAGGLE_MODELS
            ]
        }
    
    def handle_health(self) -> Dict:
        """Handle /health - return gateway and account status."""
        mgr_status = self.manager.get_status()
        
        with self._lock:
            return {
                "status": "healthy" if mgr_status['summary']['healthy'] > 0 else "degraded",
                "gateway": {
                    "uptime_seconds": time.time() - self._start_time,
                    "total_requests": self._request_count,
                    "active_sessions": len(self.sessions),
                },
                "kaggle_accounts": mgr_status,
                "timestamp": time.time()
            }
    
    def start(self) -> None:
        """Start the HTTP server."""
        if self._server:
            return
        
        handler = self._make_handler()
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._server.gateway = self  # Attach gateway instance
        
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"kaggle-gateway-{self.port}"
        )
        self._server_thread.start()
        print(f"[KaggleGateway] Started on http://127.0.0.1:{self.port}")
    
    def stop(self) -> None:
        """Stop the HTTP server and rotation manager."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        
        if self._server_thread:
            self._server_thread.join(timeout=5.0)
            self._server_thread = None
        
        self.manager.stop_rotation()
        print("[KaggleGateway] Stopped")
    
    def _make_handler(self):
        gateway = self
        
        class GatewayHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                
                if parsed.path == "/v1/models":
                    self._send_json(gateway.handle_models())
                elif parsed.path == "/health":
                    self._send_json(gateway.handle_health())
                else:
                    self._send_error(404, "Not Found")
            
            def do_POST(self):
                parsed = urlparse(self.path)
                
                if parsed.path == "/v1/chat/completions":
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode('utf-8')
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        self._send_error(400, "Invalid JSON")
                        return
                    
                    with gateway._lock:
                        gateway._request_count += 1
                    
                    response, status = gateway.handle_chat_completions(data)
                    self._send_json(response, status)
                else:
                    self._send_error(404, "Not Found")
            
            def _send_json(self, data: Dict, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
            
            def _send_error(self, status: int, message: str):
                self._send_json({"error": message}, status)
            
            def log_message(self, format, *args):
                # Suppress default logging
                pass
        
        return GatewayHandler


# Global gateway instance
_gateway: Optional[KagglePoolGateway] = None
_gateway_lock = threading.Lock()


def get_kaggle_gateway(port: int = DEFAULT_PORT) -> KagglePoolGateway:
    """Get or create the global Kaggle pool gateway."""
    global _gateway
    with _gateway_lock:
        if _gateway is None:
            _gateway = KagglePoolGateway(port)
        return _gateway


def start_kaggle_gateway(port: int = DEFAULT_PORT) -> KagglePoolGateway:
    """Start the global Kaggle pool gateway."""
    gateway = get_kaggle_gateway(port)
    gateway.start()
    return gateway


def stop_kaggle_gateway() -> None:
    """Stop the global Kaggle pool gateway."""
    global _gateway
    with _gateway_lock:
        if _gateway:
            _gateway.stop()
            _gateway = None


if __name__ == "__main__":
    import sys
    
    gateway = start_kaggle_gateway()
    
    print("Kaggle Pool Gateway running. Press Ctrl+C to stop.")
    print(f"Endpoints:")
    print(f"  POST http://127.0.0.1:{DEFAULT_PORT}/v1/chat/completions")
    print(f"  GET  http://127.0.0.1:{DEFAULT_PORT}/v1/models")
    print(f"  GET  http://127.0.0.1:{DEFAULT_PORT}/health")
    
    try:
        while True:
            time.sleep(10)
            health = gateway.handle_health()
            print(f"[Health] {health['status']} | Accounts: {health['kaggle_accounts']['summary']}")
    except KeyboardInterrupt:
        stop_kaggle_gateway()