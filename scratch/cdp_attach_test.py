"""Attach to each CDP target individually to find which one hangs Playwright."""
import base64
import json
import os
import socket
import struct
import time
import urllib.request

HOST, PORT = "127.0.0.1", 9222
LOG = os.path.join(os.path.dirname(__file__), "ws_probe.log")


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def get_ws_url():
    with urllib.request.urlopen(f"http://{HOST}:{PORT}/json/version", timeout=5) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def ws_handshake(ws_url):
    assert ws_url.startswith("ws://")
    rest = ws_url[5:]
    hostport, path = rest.split("/", 1)
    host, port = hostport.split(":")
    sock = socket.create_connection((host, int(port)), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET /{path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
        f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
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


def ws_recv_frame(sock, timeout=10):
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 2:
        hdr += sock.recv(2 - len(hdr))
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    if ln == 126:
        ext = sock.recv(2)
        ln = struct.unpack(">H", ext)[0]
    elif ln == 127:
        ext = sock.recv(8)
        ln = struct.unpack(">Q", ext)[0]
    mkey = sock.recv(4) if masked else b""
    payload = b""
    while len(payload) < ln:
        payload += sock.recv(ln - len(payload))
    if masked:
        payload = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def send_and_wait(sock, mid, method, params=None, timeout=8, session_id=None):
    msg = {"id": mid, "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    ws_send_text(sock, json.dumps(msg))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            opcode, payload = ws_recv_frame(sock, timeout=max(0.5, deadline - time.time()))
        except socket.timeout:
            return None
        if opcode == 1:
            obj = json.loads(payload)
            if obj.get("id") == mid:
                return obj
    return None


def main():
    if os.path.exists(LOG):
        os.remove(LOG)
    sock = ws_handshake(get_ws_url())
    r = send_and_wait(sock, 1, "Target.getTargets", timeout=8)
    targets = r["result"]["targetInfos"]
    log(f"targets: {len(targets)}")
    mid = 10
    for t in targets:
        tid, ttype, url = t["targetId"], t["type"], t.get("url", "")
        mid += 1
        t0 = time.time()
        r = send_and_wait(sock, mid, "Target.attachToTarget",
                          {"targetId": tid, "flatten": True}, timeout=6)
        dt = time.time() - t0
        if r is None:
            log(f"  HANG  {ttype:12s} {url[:60]!r} ({tid}) no reply in 6s")
            continue
        if "error" in r:
            log(f"  ERR   {ttype:12s} {url[:60]!r} -> {r['error']}")
            continue
        sid = r["result"]["sessionId"]
        log(f"  OK    {ttype:12s} {url[:60]!r} attached in {dt:.2f}s")
        # try a trivial command on the session
        mid += 1
        t0 = time.time()
        r2 = send_and_wait(sock, mid, "Runtime.evaluate",
                           {"expression": "1+1", "returnByValue": True},
                           timeout=6, session_id=sid)
        dt = time.time() - t0
        if r2 is None:
            log(f"        SESSION HANG: Runtime.evaluate no reply in 6s")
        elif "error" in r2:
            log(f"        session err: {r2['error']}")
        else:
            log(f"        Runtime.evaluate ok in {dt:.2f}s -> {r2['result'].get('result', {}).get('value')}")
        mid += 1
        send_and_wait(sock, mid, "Target.detachFromTarget", {"sessionId": sid}, timeout=4)
    sock.close()
    log("DONE")


if __name__ == "__main__":
    main()
