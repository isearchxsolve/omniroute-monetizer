"""Session discovery via RAW CDP (bypasses Playwright connect_over_cdp, which
hangs attaching to the hung stray renderer). Creates a fresh page target,
navigates read-only, classifies auth state. Stdlib only. Zero handoff."""
import base64
import json
import os
import socket
import struct
import time
import urllib.request

HOST, PORT = "127.0.0.1", 9222
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "state", "session_discovery.json")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discovery_run.log")

TARGETS = [
    ("openrouter", "https://openrouter.ai/settings/keys"),
    ("anthropic",  "https://platform.claude.com/settings/keys"),
    ("github",     "https://github.com/settings/tokens"),
    ("groq",       "https://console.groq.com/keys"),
    ("gemini",     "https://aistudio.google.com/apikey"),
    ("mistral",    "https://console.mistral.ai/api-keys"),
    ("cohere",     "https://dashboard.cohere.com/api-keys"),
    ("cerebras",   "https://cloud.cerebras.ai/api-keys"),
    ("sambanova",  "https://cloud.sambanova.net/apis"),
    ("together",   "https://api.together.xyz/settings/api-keys"),
    ("deepseek",   "https://platform.deepseek.com/api_keys"),
    ("xai",        "https://console.x.ai/"),
]

AUTH_SIGNALS = [
    "api key", "api keys", "create key", "create api key", "generate", "new key",
    "sk-or-", "sk-ant-", "gsk_", "key name", "your keys", "token", "secret",
]
WALL_SIGNALS = [
    "sign in", "log in", "login", "sign up", "continue with google", "continue with github",
    "email address", "password", "welcome back", "create account",
]
CAPTCHA_SIGNALS = ["captcha", "hcaptcha", "recaptcha", "turnstile", "verify you are human"]


def log(msg):
    print(msg, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# ---------- raw websocket helpers (proven in cdp_attach_test.py) ----------

def get_ws_url():
    with urllib.request.urlopen(f"http://{HOST}:{PORT}/json/version", timeout=8) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def ws_connect(ws_url):
    rest = ws_url[5:]
    hostport, path = rest.split("/", 1)
    host, port = hostport.split(":")
    sock = socket.create_connection((host, int(port)), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET /{path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
           f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    sock.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("closed during handshake")
        resp += chunk
    if b"101" not in resp.split(b"\r\n", 1)[0]:
        raise RuntimeError(f"bad handshake: {resp[:200]!r}")
    return sock


def ws_send_text(sock, text):
    data = text.encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sock.sendall(bytes(header) + mask + masked)


def ws_recv_frame(sock, timeout):
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 2:
        hdr += sock.recv(2 - len(hdr))
    b2 = hdr[1]
    ln = b2 & 0x7F
    if ln == 126:
        ext = b""
        while len(ext) < 2:
            ext += sock.recv(2 - len(ext))
        ln = struct.unpack(">H", ext)[0]
    elif ln == 127:
        ext = b""
        while len(ext) < 8:
            ext += sock.recv(8 - len(ext))
        ln = struct.unpack(">Q", ext)[0]
    mkey = sock.recv(4) if (b2 & 0x80) else b""
    payload = b""
    while len(payload) < ln:
        payload += sock.recv(ln - len(payload))
    if mkey:
        payload = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload))
    return hdr[0] & 0x0F, payload


class CDP:
    """Minimal CDP client over one browser websocket, with session support."""

    def __init__(self):
        self.sock = ws_connect(get_ws_url())
        self.mid = 0

    def send(self, method, params=None, session_id=None, timeout=30):
        self.mid += 1
        mid = self.mid
        msg = {"id": mid, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        ws_send_text(self.sock, json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                opcode, payload = ws_recv_frame(self.sock, max(0.5, deadline - time.time()))
            except socket.timeout:
                return None
            if opcode != 1:
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if obj.get("id") == mid:
                return obj
        return None

    def call(self, method, params=None, session_id=None, timeout=30):
        r = self.send(method, params, session_id, timeout)
        if r is None:
            raise TimeoutError(f"{method} no reply in {timeout}s")
        if "error" in r:
            raise RuntimeError(f"{method} error: {r['error']}")
        return r.get("result", {})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def save(results):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results}, f, indent=2)


def probe(cdp, sid, name, url):
    t0 = time.time()
    try:
        nav = cdp.call("Page.navigate", {"url": url}, session_id=sid, timeout=35)
        if nav.get("errorText"):
            return {"provider": name, "target_url": url, "status": "NAV_ERROR",
                    "error": nav["errorText"][:150], "elapsed": round(time.time() - t0, 1)}
    except Exception as e:
        return {"provider": name, "target_url": url, "status": "NAV_ERROR",
                "error": str(e)[:150], "elapsed": round(time.time() - t0, 1)}
    # poll readyState until complete (max 25s)
    deadline = time.time() + 25
    ready = ""
    while time.time() < deadline:
        try:
            r = cdp.call("Runtime.evaluate",
                         {"expression": "document.readyState", "returnByValue": True},
                         session_id=sid, timeout=8)
            ready = r.get("result", {}).get("value", "")
            if ready == "complete":
                break
        except Exception:
            pass
        time.sleep(0.7)
    time.sleep(2.5)  # SPA hydration
    final_url, title, body = url, "", ""
    try:
        r = cdp.call("Runtime.evaluate", {"expression":
            "JSON.stringify({u: location.href, t: document.title, "
            "b: (document.body && document.body.innerText || '').slice(0, 3000)})",
            "returnByValue": True}, session_id=sid, timeout=10)
        v = r.get("result", {}).get("value", "{}")
        d = json.loads(v)
        final_url, title, body = d.get("u", url), d.get("t", ""), d.get("b", "")
    except Exception as e:
        log(f"    read err: {str(e)[:100]}")
    low = (body + " " + title).lower()
    auth_hits = [s for s in AUTH_SIGNALS if s in low]
    wall_hits = [s for s in WALL_SIGNALS if s in low]
    if any(s in low for s in CAPTCHA_SIGNALS):
        status = "CAPTCHA_DISCARD"
    elif wall_hits and not auth_hits:
        status = "NOT_AUTHENTICATED"
    elif auth_hits:
        status = "AUTHENTICATED"
    else:
        status = "UNKNOWN"
    return {"provider": name, "target_url": url, "final_url": final_url,
            "title": title[:80], "status": status, "ready": ready,
            "auth_hits": auth_hits[:5], "wall_hits": wall_hits[:5],
            "body_snippet": body[:200].replace("\n", " | "),
            "elapsed": round(time.time() - t0, 1)}


def main():
    if os.path.exists(LOG):
        os.remove(LOG)
    cdp = CDP()
    log("connected to browser CDP")
    # fresh target — never touch the hung stray
    res = cdp.call("Target.createTarget", {"url": "about:blank"}, timeout=15)
    tid = res["targetId"]
    log(f"created fresh target {tid}")
    res = cdp.call("Target.attachToTarget", {"targetId": tid, "flatten": True}, timeout=15)
    sid = res["sessionId"]
    log(f"attached session {sid[:16]}...")
    cdp.call("Page.enable", session_id=sid, timeout=10)
    cdp.call("Runtime.enable", session_id=sid, timeout=10)
    results = []
    try:
        for name, url in TARGETS:
            r = probe(cdp, sid, name, url)
            log(f"{name:12s} {r['status']:20s} -> {r.get('final_url', '')[:90]}")
            results.append(r)
            save(results)
    finally:
        try:
            cdp.call("Target.closeTarget", {"targetId": tid}, timeout=10)
        except Exception:
            pass
        cdp.close()
        save(results)
    auth = [r["provider"] for r in results if r["status"] == "AUTHENTICATED"]
    log("AUTHENTICATED: " + (", ".join(auth) if auth else "none"))
    log(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
