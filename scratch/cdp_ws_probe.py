"""Raw CDP WebSocket probe (stdlib only). Tests whether Chrome's CDP backend
answers commands at all, bypassing Playwright. Prints timing."""
import json, socket, base64, os, time, urllib.request

def get_ws_url():
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=10) as r:
        data = json.loads(r.read().decode())
    return data["webSocketDebuggerUrl"], data.get("Browser", "?")

def ws_handshake(sock, host, port, path):
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
           f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    sock.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("connection closed during handshake")
        resp += chunk
    status = resp.split(b"\r\n", 1)[0].decode()
    return status

def ws_send_text(sock, text):
    payload = text.encode()
    mask = os.urandom(4)
    header = bytearray([0x81])  # FIN + text
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += n.to_bytes(2, "big")
    else:
        header.append(0x80 | 127)
        header += n.to_bytes(8, "big")
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + masked)

def ws_recv_frame(sock, timeout=20):
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 2:
        hdr += sock.recv(2 - len(hdr))
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    length = b2 & 0x7F
    if length == 126:
        ext = b""
        while len(ext) < 2:
            ext += sock.recv(2 - len(ext))
        length = int.from_bytes(ext, "big")
    elif length == 127:
        ext = b""
        while len(ext) < 8:
            ext += sock.recv(8 - len(ext))
        length = int.from_bytes(ext, "big")
    data = b""
    while len(data) < length:
        data += sock.recv(length - len(data))
    return opcode, data

def send_and_wait(sock, mid, method, params=None, timeout=15):
    msg = {"id": mid, "method": method}
    if params: msg["params"] = params
    ws_send_text(sock, json.dumps(msg))
    t0 = time.time()
    while True:
        try:
            opcode, data = ws_recv_frame(sock, timeout=timeout)
        except socket.timeout:
            return None, f"TIMEOUT after {time.time()-t0:.1f}s"
        try:
            obj = json.loads(data.decode(errors="replace"))
        except Exception:
            continue
        if obj.get("id") == mid:
            return obj, f"ok in {time.time()-t0:.2f}s"

def main():
    ws_url, browser = get_ws_url()
    print(f"browser={browser}", flush=True)
    rest = ws_url.split("://", 1)[1]
    hostport, path = rest.split("/", 1)
    host, port = hostport.split(":")
    path = "/" + path
    s = socket.create_connection((host, int(port)), timeout=10)
    print("handshake:", ws_handshake(s, host, port, path), flush=True)

    steps = [
        ("Browser.getVersion", None),
        ("Target.setDiscoverTargets", {"discover": True}),
        ("Target.getTargets", None),
        ("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}),
    ]
    mid = 0
    for method, params in steps:
        mid += 1
        resp, note = send_and_wait(s, mid, method, params, timeout=15)
        if resp is None:
            print(f"STEP {method}: {note}  <-- HANGS HERE", flush=True)
            break
        if method == "Target.getTargets":
            tg = resp.get("result", {}).get("targetInfos", [])
            print(f"STEP {method}: {note} -> {len(tg)} targets", flush=True)
            for t in tg:
                print(f"    {t.get('type'):10s} attached={t.get('attached')} {t.get('url','')[:70]}", flush=True)
        else:
            print(f"STEP {method}: {note}", flush=True)
    s.close()

if __name__ == "__main__":
    main()
