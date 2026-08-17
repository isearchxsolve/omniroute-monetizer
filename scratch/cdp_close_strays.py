"""Close stray/hung page targets via raw CDP so Playwright connect_over_cdp
doesn't hang attaching to a dead renderer. Keeps about:blank. Stdlib only."""
import json, socket, base64, os, time, urllib.request

def get_ws_url():
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=10) as r:
        return json.loads(r.read().decode())["webSocketDebuggerUrl"]

def ws_handshake(sock, host, port, path):
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
           f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    sock.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk: raise RuntimeError("closed")
        resp += chunk

def ws_send_text(sock, text):
    payload = text.encode(); mask = os.urandom(4)
    header = bytearray([0x81]); n = len(payload)
    if n < 126: header.append(0x80 | n)
    elif n < 65536: header.append(0x80 | 126); header += n.to_bytes(2, "big")
    else: header.append(0x80 | 127); header += n.to_bytes(8, "big")
    header += mask
    sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

def ws_recv_frame(sock, timeout=15):
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 2: hdr += sock.recv(2 - len(hdr))
    length = hdr[1] & 0x7F
    if length == 126:
        ext = b""
        while len(ext) < 2: ext += sock.recv(2 - len(ext))
        length = int.from_bytes(ext, "big")
    elif length == 127:
        ext = b""
        while len(ext) < 8: ext += sock.recv(8 - len(ext))
        length = int.from_bytes(ext, "big")
    data = b""
    while len(data) < length: data += sock.recv(length - len(data))
    return hdr[0] & 0x0F, data

def send_and_wait(sock, mid, method, params=None, timeout=15):
    msg = {"id": mid, "method": method}
    if params: msg["params"] = params
    ws_send_text(sock, json.dumps(msg))
    t0 = time.time()
    while True:
        try:
            _, data = ws_recv_frame(sock, timeout=timeout)
        except socket.timeout:
            return None
        try: obj = json.loads(data.decode(errors="replace"))
        except Exception: continue
        if obj.get("id") == mid: return obj

def main():
    ws_url = get_ws_url()
    rest = ws_url.split("://", 1)[1]
    hostport, path = rest.split("/", 1)
    host, port = hostport.split(":")
    s = socket.create_connection((host, int(port)), timeout=10)
    ws_handshake(s, host, port, "/" + path)

    resp = send_and_wait(s, 1, "Target.getTargets")
    targets = resp.get("result", {}).get("targetInfos", [])
    print(f"targets before: {len(targets)}", flush=True)
    mid = 1
    # create a fresh responsive page target FIRST so Chrome never has zero
    # page targets (closing the last tab would exit the browser)
    mid += 1
    r = send_and_wait(s, mid, "Target.createTarget", {"url": "about:blank"}, timeout=10)
    new_id = (r or {}).get("result", {}).get("targetId", "FAILED")
    print(f"  NEW   {new_id}", flush=True)
    closed = 0
    for t in targets:
        if t.get("type") != "page":
            continue
        url = t.get("url", "")
        # close ALL pre-existing page targets (even empty-url ones can have
        # hung renderers that block Playwright's connect-time initialization)
        mid += 1
        r = send_and_wait(s, mid, "Target.closeTarget", {"targetId": t["targetId"]}, timeout=10)
        ok = bool(r and r.get("result", {}).get("success", False))
        closed += 1
        print(f"  CLOSE {t['targetId'][:12]} {url!r} -> success={ok}", flush=True)
    print(f"closed={closed} new_target={new_id}", flush=True)
    s.close()

if __name__ == "__main__":
    main()
