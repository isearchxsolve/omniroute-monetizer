"""session_pool_shim.py -- HTTP face for session_pool.py

Provides an OpenAI-compatible /v1/chat/completions endpoint over the SessionPool.
Listens on port 8190 by default.
"""
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from session_pool import SessionPool, ChatError

# Initialize global pool
pool = SessionPool()

class ShimHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
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
        model = req.get("model", "auto")
        
        try:
            # Route strictly to chat modality
            result = pool.chat(messages, model=model, modality="chat")
        except ChatError as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": str(e)}}).encode())
            return
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": str(e)}}).encode())
            return
            
        # Format response as OpenAI chat completion
        resp = {
            "id": f"chatcmpl-{int(time.time()*1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.get("label", model),
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

def run(port=8190):
    server = ThreadingHTTPServer(("127.0.0.1", port), ShimHandler)
    print(f"SessionPool Shim listening on http://127.0.0.1:{port}/v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8190
    run(port)
