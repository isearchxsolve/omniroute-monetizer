"""Find v0.app's response channel: send via the API, then watch ALL network for 20s
to see where the model answer streams (SSE GET? websocket? poll?)."""
import sys, json, time, urllib.request
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from capture_sessions_cdp import CDP, targets

PORT = 9222
tabs = targets(PORT)
t = next((x for x in tabs if "v0.app" in x.get("url", "")), None)
if not t:
    print("no v0 tab"); sys.exit(0)
print("tab:", t["url"][:80])

c = CDP(t["webSocketDebuggerUrl"])
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(1.0)
except Exception: pass
c.call("Runtime.enable", timeout=20)
c.call("Network.enable")

# Send a fresh prompt via the recorded API (cleaner than composer)
import pathlib
from curl_cffi.requests import Session as CC
p = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_v0_app.json")
d = json.loads(p.read_text(encoding="utf-8-sig"))
rx = d["recorded_exchange"]
SENT = "Reply exactly one word: Omni."
body = rx["request_body"].replace(SENT, "Reply exactly one word: Beacon.")
hdrs = {k: v for k, v in rx.get("request_headers", {}).items() if not k.startswith(":")}
hdrs.pop("content-length", None); hdrs.pop("Content-Length", None)
hdrs["cookie"] = d.get("cookie_header", "")
s = CC(impersonate="chrome")
r = s.post(rx["url"], data=body.encode(), headers=hdrs, timeout=60)
print("send status:", r.status_code, "body:", repr(r.text[:40]))

# Now watch the tab's network for 20s
print("\n--- watching tab network 20s ---")
seen = {}
t0 = time.time()
while time.time() - t0 < 20:
    for ev in list(c.events):
        m = ev.get("method"); prm = ev.get("params") or {}
        if m == "Network.requestWillBeSent":
            u = (prm.get("request") or {}).get("url", "")
            meth = (prm.get("request") or {}).get("method", "")
            rid = prm.get("requestId")
            seen[rid] = (meth, u)
        elif m == "Network.webSocketFrameReceived":
            pl = str((prm.get("response") or {}).get("payloadData") or "")
            print(f"  WS-FRAME ({len(pl)}B): {pl[:120]!r}")
        elif m == "Network.responseReceived":
            rid = prm.get("requestId")
            resp = prm.get("response") or {}
            ct = (resp.get("headers") or {}).get("content-type", "")
            if rid in seen:
                meth, u = seen[rid]
                print(f"  {meth:5s} {resp.get('status')} {ct[:30]:30s} {u[:90]}")
    time.sleep(0.3)
print("\ndone")
