#!/usr/bin/env python3
"""
Minimal local voice-chat proxy for TokenRouter.
- Serves index.html at /
- POST /chat -> forwards to TokenRouter /v1/chat/completions
- Rotates across live keys on 401/403/429 (revoked or rate-limited)
Stdlib only. No installs.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = "https://api.tokenrouter.com/v1/chat/completions"
MODEL = "qwen/qwen3.8-max-free"
PORT = 8080

KEYS_FILE = os.path.join(HERE, "keys.json")


def load_keys():
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [k for k in data.get("keys", []) if k.get("live", True)]


STATE = {"keys": load_keys(), "idx": 0}


def next_key(skip_current=False):
    keys = STATE["keys"]
    if not keys:
        return None
    if skip_current:
        STATE["idx"] = (STATE["idx"] + 1) % len(keys)
    return keys[STATE["idx"]]["key"]


def call_upstream(messages):
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": 1024,
    }).encode("utf-8")

    last_err = "no keys available"
    for _ in range(len(STATE["keys"])):
        key = next_key()
        if not key:
            break
        req = urllib.request.Request(
            UPSTREAM,
            data=payload,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = body["choices"][0]["message"]["content"]
                return {"ok": True, "text": text}
        except urllib.error.HTTPError as e:
            last_err = "HTTP {} from upstream".format(e.code)
            if e.code in (401, 403, 429):
                # revoked or rate-limited -> rotate to next key
                next_key(skip_current=True)
                continue
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
                last_err += ": " + detail
            except Exception:
                pass
            break
        except Exception as e:
            last_err = str(e)
            break
    return {"ok": False, "error": last_err}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] " + fmt % args + "\n")

    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, raw=f.read(), ctype="text/html; charset=utf-8")
        elif self.path == "/health":
            self._send(200, {"ok": True, "keys_loaded": len(STATE["keys"])})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/chat":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            messages = data.get("messages", [])
            if not messages:
                self._send(400, {"ok": False, "error": "empty messages"})
                return
            result = call_upstream(messages)
            self._send(200 if result["ok"] else 502, result)
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    print("voice proxy on http://localhost:{} ({} keys loaded)".format(
        PORT, len(STATE["keys"])))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
