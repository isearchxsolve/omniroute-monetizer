"""P2 build-step 2: DIRECT websocket connection test from Python.
Open wss://gateway.meta.ai/ws with the seat's cookies (names only in logs).
Success = handshake 101 -> transport is stateless-capable. Then listen for any
server-initiated frames (init/hello) and try sending nothing first."""
import io, json, sys, time, pathlib, ssl
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import websocket

seat = json.loads(pathlib.Path("state/secrets/session_meta_ai_web.json").read_text(encoding="utf-8"))
cookie = seat.get("cookie_header", "")
URL = "wss://gateway.meta.ai/ws"

sslopt = {"cert_reqs": ssl.CERT_NONE}
headers = {
    "Cookie": cookie,
    "Origin": "https://www.meta.ai",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}

print("connecting to", URL, "...")
try:
    ws = websocket.create_connection(
        URL, header=headers, sslopt=sslopt, timeout=15,
        suppress_origin=True,
    )
    print("CONNECTED! status ok, subprotocol:", ws.subprotocol)
    # listen for server-initiated frames for up to 10s
    ws.settimeout(3.0)
    got = []
    end = time.monotonic() + 10
    while time.monotonic() < end:
        try:
            op, data = ws.recv_data(control_frame=False)
            if isinstance(data, bytes):
                got.append({"op": op, "len": len(data), "head": data[:40].hex()})
                print("RECV op=%d len=%d head=%s" % (op, len(data), data[:40].hex()))
            else:
                got.append({"op": op, "len": len(data), "head": str(data)[:120]})
                print("RECV op=%d len=%d head=%s" % (op, len(data), str(data)[:120]))
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as e:
            print("recv error:", type(e).__name__, str(e)[:120]); break
    if not got:
        print("no server-initiated frames within 10s (client must speak first)")
    ws.close()
    pathlib.Path("state/meta_ws_direct_test.json").write_text(
        json.dumps({"connected": True, "subprotocol": ws.subprotocol, "frames": got}, indent=1),
        encoding="utf-8")
    print("saved -> state/meta_ws_direct_test.json")
except Exception as e:
    print("CONNECT FAILED:", type(e).__name__, str(e)[:300])
    pathlib.Path("state/meta_ws_direct_test.json").write_text(
        json.dumps({"connected": False, "error": "%s: %s" % (type(e).__name__, str(e)[:300])}, indent=1),
        encoding="utf-8")
