import argparse
import json
import pathlib
import time
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
import websocket

DEFAULT_PORT = 9222
SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")

# We re-use the exact same LLM payload injector logic from auto_generate_agent
from auto_generate_agent import extract_and_identify, JS_EXECUTE_ACTION

def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""

class Page:
    def __init__(self, target_id: str, port: int = 9222, timeout: int = 30):
        raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=15).read()
        ws_url = None
        for p in json.loads(raw):
            if p.get("id") == target_id:
                ws_url = p.get("webSocketDebuggerUrl")
                break
        if not ws_url:
            raise RuntimeError(f"Target {target_id} not found")
        self.ws = websocket.create_connection(ws_url, timeout=timeout, max_size=96 * 1024 * 1024)
        self._id = 0

    def __enter__(self): return self
    def __exit__(self, *_): self.ws.close()

    def send(self, method: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
        self._id += 1
        mine = self._id
        self.ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(1.0, deadline - time.time()))
            try:
                got = json.loads(self.ws.recv())
                if got.get("id") == mine:
                    if "error" in got:
                        raise RuntimeError(f"{method}: {got['error'].get('message')}")
                    return got.get("result", {})
            except websocket.WebSocketTimeoutException:
                pass
        raise TimeoutError(f"{method} timed out")

    def evaluate(self, js: str, timeout: int = 15) -> str:
        res = self.send("Runtime.evaluate", {"expression": js, "awaitPromise": True}, timeout=timeout)
        if "exceptionDetails" in res:
            return "EXCEPTION: " + str(res["exceptionDetails"])
        val = res.get("result", {})
        return val.get("value", val.get("unserializableValue", str(val)))

def run_harvest(target: dict, port: int):
    target_id = target["id"]
    url = target.get("url", "")
    title = target.get("title", "")[:30]
    h = _host(url)
    
    if not h or not url.startswith("http") or any(s in h for s in ("google.com", "gstatic.com", "chrome://", "newtab")):
        return

    print(f"\n[{h}] Analyzing {title}...")
    try:
        with Page(target_id, port=port, timeout=30) as p:
            input_id, button_id = extract_and_identify(p, title)
            if not input_id or not button_id:
                print(f"[{h}] LLM could not identify elements. Skipping.")
                return

            print(f"[{h}] Found input='{input_id}', button='{button_id}'")
            
            p.send("Network.enable", timeout=10)
            
            # Flush old events
            while True:
                p.ws.settimeout(0.1)
                try: p.ws.recv()
                except: break
            
            # Execute generation
            js = JS_EXECUTE_ACTION.replace('{input_id}', input_id).replace('{button_id}', button_id)
            js = js.replace('{prompt_json}', json.dumps("Reply exactly one word: Omni."))
            print(f"[{h}] Clicking generate...")
            res = p.evaluate(js, timeout=20)
            if res != "SUCCESS":
                print(f"[{h}] Generate click failed: {res}")
                return
            
            print(f"[{h}] Waiting for network exchange...")
            reqs = {}
            extra = {}
            resp = {}
            seen = None
            finished = False
            deadline = time.time() + 15
            
            while time.time() < deadline and not finished:
                p.ws.settimeout(1.0)
                try:
                    msg = json.loads(p.ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception:
                    continue
                
                meth, pr = msg.get("method"), msg.get("params", {})
                
                if meth == "Network.requestWillBeSent":
                    r = pr.get("request", {})
                    # Look for the first POST after we clicked
                    if r.get("method") == "POST" and "image" not in (r.get("url") or ""):
                        rid = pr.get("requestId")
                        reqs[rid] = {
                            "url": r.get("url"),
                            "method": r.get("method"),
                            "headers": r.get("headers", {}),
                            "postData": r.get("postData"),
                            "hasPostData": r.get("hasPostData")
                        }
                        if seen is None:
                            seen = rid
                            print(f"[{h}] Captured POST to {r.get('url')[:60]}")
                elif meth == "Network.requestWillBeSentExtraInfo":
                    rid = pr.get("requestId")
                    if rid in reqs:
                        extra[rid] = pr.get("headers", {})
                elif meth == "Network.responseReceived":
                    rid = pr.get("requestId")
                    if rid == seen:
                        rr = pr.get("response", {})
                        resp[rid] = {"status": rr.get("status"), "headers": rr.get("headers", {})}
                elif meth == "Network.loadingFinished":
                    if pr.get("requestId") == seen and seen is not None:
                        finished = True
            
            if seen is None:
                print(f"[{h}] No POST request seen within 15s!")
                return
                
            req = reqs[seen]
            actual_headers = extra.get(seen, {})
            # merge headers (extra has cookie and HTTP2 pseudo headers)
            for k, v in actual_headers.items():
                req["headers"][k] = v
                
            # fetch cookies
            cookies = p.send("Network.getCookies").get("cookies", [])
            
            state = {}
            out = SECRETS / f"session_{h.replace('.', '_')}.json"
            if out.exists():
                try:
                    state = json.loads(out.read_text(encoding="utf-8"))
                except: pass
                
            state["host"] = h
            state["cookies"] = cookies
            state["recorded_exchange"] = {
                "url": req["url"],
                "method": req["method"],
                "request_headers": req["headers"],
                "request_body": req["postData"],
                "response_headers": resp.get(seen, {}).get("headers", {}),
                "response_status": resp.get(seen, {}).get("status", 200)
            }
            
            out.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"[{h}] SAVED recorded_exchange to {out.name}!")
            
    except Exception as e:
        print(f"[{h}] Error: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    
    raw = urllib.request.urlopen(f"http://127.0.0.1:{args.port}/json").read()
    pages = [p for p in json.loads(raw) if p.get("type") == "page"]
    
    print(f"Found {len(pages)} pages.")
    for p in pages:
        run_harvest(p, args.port)
