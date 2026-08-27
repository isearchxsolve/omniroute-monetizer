# Re-probe EVERY video tab on all ports with full error surfacing. The previous
# classifier printed "NOJS" without the underlying error -- that is not evidence a
# tab is frozen, it is an unexplained probe failure (Chrome Gap Doctrine: classify
# against (a) send-time/probe gap, (b) real death, (c) capture bug -- with evidence).
# This run prints the EXACT CDP error for each tab, uses a cheap document.title eval
# first (no body reflow), a fresh websocket per tab, and Runtime.enable beforehand.
import json
import time
import pathlib
import urllib.request
import websocket

PORTS = (9222, 9223, 9224, 9225)

VIDEO_TOKENS = (
    "flow", "veo", "video", "labs.google", "veoaifree", "digen", "rtst", "kie",
    "runway", "pika", "kling", "hailuo", "luma", "genmo", "haiper", "invideo",
    "synthesia", "heygen", "akool", "creen", "minimax", "pixverse", "viggle",
    "seedance", "firefly", "adobe", "nemo", "vidu", "mochi", "dreamina",
    "higgsfield", "freepik", "rendernet", "pollo", "vmake", "magichour", "giz",
)

def is_video(t):
    blob = (t.get("url", "") + " " + t.get("title", "")).lower()
    return any(tok in blob for tok in VIDEO_TOKENS)

def cdp(ws, mid, method, params=None, timeout=30):
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(1.0, deadline - time.time()))
        try:
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        if msg.get("id") == mid:
            return msg
    return {"error": {"message": f"TIMEOUT after {timeout}s waiting for {method}"}}

results = []
for port in PORTS:
    try:
        raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=6).read()
        tabs = json.loads(raw)
    except Exception as e:
        print(f":{port} NO_BROWSER {type(e).__name__}")
        continue
    pages = [t for t in tabs if t.get("type") == "page" and is_video(t)]
    print(f"\n===== :{port}  {len(pages)} video tabs =====")
    for i, t in enumerate(pages):
        url = t.get("url", "")
        host = url.split("/")[2] if "://" in url else "?"
        ws_url = t.get("webSocketDebuggerUrl") or ""
        if not ws_url:
            print(f"  [NO_WS_URL ] {host:22s} target listed but webSocketDebuggerUrl EMPTY")
            results.append({"port": port, "host": host, "url": url, "verdict": "NO_WS_URL"})
            continue
        try:
            ws = websocket.create_connection(ws_url, timeout=15, max_size=8 * 1024 * 1024)
        except Exception as e:
            print(f"  [WS_CONNECT] {host:22s} {type(e).__name__}: {str(e)[:80]}")
            results.append({"port": port, "host": host, "url": url,
                            "verdict": "WS_CONNECT_FAIL", "err": str(e)[:120]})
            continue
        try:
            r0 = cdp(ws, 1, "Runtime.enable", timeout=15)
            r1 = cdp(ws, 2, "Runtime.evaluate",
                     {"expression": "JSON.stringify({t: document.title, u: location.href, rs: document.readyState})",
                      "returnByValue": True}, timeout=30)
            if "error" in r1:
                em = r1["error"].get("message", "")[:120]
                print(f"  [EVAL_ERR  ] {host:22s} {em}")
                results.append({"port": port, "host": host, "url": url,
                                "verdict": "EVAL_ERROR", "err": em})
                continue
            res = r1.get("result", {})
            if res.get("exceptionDetails"):
                d = res["exceptionDetails"]
                em = str(d.get("exception", {}).get("description") or d.get("text"))[:120]
                print(f"  [JS_THROW  ] {host:22s} {em}")
                results.append({"port": port, "host": host, "url": url,
                                "verdict": "JS_THROW", "err": em})
                continue
            val = res.get("result", {}).get("value")
            if not val:
                print(f"  [NO_VALUE  ] {host:22s} evaluate returned no value")
                results.append({"port": port, "host": host, "url": url, "verdict": "NO_VALUE"})
                continue
            d = json.loads(val)
            print(f"  [LIVE      ] {host:22s} readyState={d.get('rs'):10s} title={str(d.get('t'))[:44]}")
            results.append({"port": port, "host": host, "url": url,
                            "verdict": "LIVE", "readyState": d.get("rs"), "title": d.get("t")})
        finally:
            try:
                ws.close()
            except Exception:
                pass
        time.sleep(0.3)   # be gentle: rapid ws churn can trip Chrome's per-target limits

from collections import Counter
c = Counter(r["verdict"] for r in results)
print(f"\n===== VERDICTS across {len(results)} video tabs =====")
for k, v in c.most_common():
    print(f"  {k:14s} {v}")
notlive = [r for r in results if r["verdict"] != "LIVE"]
if notlive:
    print("\nNON-LIVE (with exact error):")
    for r in notlive:
        print(f"  :{r['port']} {r['host']:22s} {r['verdict']:14s} {r.get('err','')}")
        print(f"      {r['url'][:90]}")
else:
    print("\nALL video tabs are LIVE -- the earlier NOJS was a probe defect, not frozen tabs.")

out = pathlib.Path("state/video_tab_liveness_reprobe.json")
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
