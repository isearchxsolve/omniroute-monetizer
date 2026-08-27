# Retry the 8 EVAL_ERR tabs on :9225 with a gentler probe. Hypothesis: the tabs
# were mid-hydration right after the operator's reload; a minimal eval with a
# longer budget and no Runtime.enable chatter should get through. If a tab STILL
# times out, we additionally check Page.getNavigationHistory (a CDP domain that
# does not require JS execution at all) to distinguish "JS busy" from "tab dead".
import json
import time
import pathlib
import urllib.request
import websocket

PORT = 9225
RETRY_HOSTS = {"rtst.ai", "app.heygen.com", "akool.com", "digen.ai",
               "veoaifree.com", "magichour.ai", "www.giz.ai"}

raw = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=6).read()
tabs = json.loads(raw)
pages = [t for t in tabs if t.get("type") == "page"]

def cdp(ws, mid, method, params=None, timeout=45):
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
for t in pages:
    url = t.get("url", "")
    host = url.split("/")[2] if "://" in url else "?"
    if host not in RETRY_HOSTS:
        continue
    ws_url = t.get("webSocketDebuggerUrl") or ""
    rec = {"port": PORT, "host": host, "url": url}
    if not ws_url:
        rec["verdict"] = "NO_WS_URL"
        results.append(rec)
        print(f"  [NO_WS_URL ] {host:22s}")
        continue
    try:
        ws = websocket.create_connection(ws_url, timeout=15, max_size=8 * 1024 * 1024)
    except Exception as e:
        rec["verdict"] = "WS_CONNECT_FAIL"
        rec["err"] = str(e)[:100]
        results.append(rec)
        print(f"  [WS_CONNECT] {host:22s} {type(e).__name__}")
        continue
    try:
        # Minimal eval, 45s budget, no Runtime.enable first.
        r1 = cdp(ws, 1, "Runtime.evaluate",
                 {"expression": "document.readyState", "returnByValue": True}, timeout=45)
        if "error" not in r1 and not r1.get("result", {}).get("exceptionDetails"):
            val = r1.get("result", {}).get("result", {}).get("value")
            r2 = cdp(ws, 2, "Runtime.evaluate",
                     {"expression": "document.title", "returnByValue": True}, timeout=20)
            title = r2.get("result", {}).get("result", {}).get("value", "?") if "error" not in r2 else "?"
            rec["verdict"] = "LIVE"
            rec["readyState"] = val
            rec["title"] = title
            print(f"  [LIVE      ] {host:22s} rs={val:11s} title={str(title)[:48]}")
        else:
            # JS eval failed/timed out -- use a NON-JS CDP domain to check tab liveness.
            nav = cdp(ws, 3, "Page.getNavigationHistory", timeout=20)
            if "error" not in nav:
                entries = nav.get("result", {}).get("entries", [])
                cur = nav.get("result", {}).get("currentIndex", -1)
                entry = entries[cur] if 0 <= cur < len(entries) else {}
                rec["verdict"] = "JS_BUSY_TAB_ALIVE"
                rec["nav_url"] = entry.get("url", "")[:100]
                rec["nav_title"] = entry.get("title", "")[:60]
                rec["err"] = r1.get("error", {}).get("message", "")[:80]
                print(f"  [JS_BUSY   ] {host:22s} tab alive per navigation history: {rec['nav_title']}")
            else:
                rec["verdict"] = "UNRESPONSIVE"
                rec["err"] = (r1.get("error", {}).get("message", "") + " | nav: " +
                              nav.get("error", {}).get("message", ""))[:140]
                print(f"  [UNRESPONS ] {host:22s} {rec['err']}")
        results.append(rec)
    finally:
        try:
            ws.close()
        except Exception:
            pass
    time.sleep(0.5)

from collections import Counter
print(f"\n===== RETRY VERDICTS ({len(results)} tabs) =====")
for k, v in Counter(r["verdict"] for r in results).most_common():
    print(f"  {k:16s} {v}")
out = pathlib.Path("state/rescan_seat4_retry.json")
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"wrote {out}")
