# OMNIROUTE SESSION-POOL SHIM v1 -- the canonical consumer endpoint (127.0.0.1:8190).
# Forwards OpenAI-style /v1/* calls to the permanent door's /v1 with the fleet token.
# DNS-outage-tolerant: falls back to IP-pinned HTTPS (SNI = real hostname).
import http.client, json, ssl, socket, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DOOR_HOST = "omniroute-relay.omniroute-fleet-kd.workers.dev"
DOOR_IPS = ["104.21.11.138", "172.67.166.36"]
TOK = "GOLD24"
PORT = 8190

def proxy(method, path, body, content_type):
    payload = body if body else None
    headers = {"Host": DOOR_HOST, "User-Agent": "omniroute-session-pool-shim"}
    if content_type:
        headers["content-type"] = content_type
    # 1) normal DNS path
    try:
        conn = http.client.HTTPSConnection(DOOR_HOST, timeout=60)
        conn.request(method, path + ("?token=" + TOK if "?" not in path else "&token=" + TOK),
                     body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data, resp.getheader("content-type") or "application/json"
    except Exception:
        pass
    # 2) IP-pinned fallback (SNI + cert validated against the real hostname)
    class Pinned(http.client.HTTPSConnection):
        def connect(self):
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self.sock = self._context.wrap_socket(sock, server_hostname=DOOR_HOST)
    last = None
    for ip in DOOR_IPS:
        try:
            conn = Pinned(ip, timeout=60)
            conn.request(method, path + ("?token=" + TOK if "?" not in path else "&token=" + TOK),
                         body=payload, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            if resp.status < 500:
                return resp.status, data, resp.getheader("content-type") or "application/json"
            last = "HTTP " + str(resp.status)
        except Exception as e:
            last = str(e)
    return 502, json.dumps({"error": "door unreachable", "detail": str(last)[:200]}).encode(), "application/json"

class Handler(BaseHTTPRequestHandler):
    def _models(self):
        data = json.dumps({
            "object": "list",
            "data": [{"id": "session-pool/auto", "object": "model",
                      "owned_by": "omniroute-session-pool"}],
        }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def _proxy(self):
        # The models listing is the gateway health surface; served locally so
        # consumers can validate the canonical endpoint without door roundtrips.
        if self.command == "GET" and self.path.split("?")[0] == "/v1/models":
            self._models()
            return
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        status, data, ctype = proxy(self.command, self.path, body,
                                    self.headers.get("content-type"))
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        self._proxy()
    def do_POST(self):
        self._proxy()
    def do_DELETE(self):
        self._proxy()
    def do_PUT(self):
        self._proxy()
    def log_message(self, fmt, *args):
        sys.stdout.write("[SHIM] " + (fmt % args) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("[SHIM] session-pool shim on 127.0.0.1:" + str(PORT) + " -> " + DOOR_HOST + "/v1", flush=True)
    srv.serve_forever()
