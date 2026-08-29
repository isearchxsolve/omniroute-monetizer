import json
import time
import urllib.request
import urllib.parse
from capture_sessions_cdp import CDP, targets, JS_SEND

def find_deepseek_tab(port: int = 9222):
    for t in targets(port):
        url = t.get("url", "")
        if "chat.deepseek.com" in url and "webSocketDebuggerUrl" in t:
            return t
    return None

def trace_pow():
    port = 9222
    t = find_deepseek_tab(port)
    if not t:
        print("No live DeepSeek tab found on port", port)
        return

    print(f"Connecting to {t['title']} ({t['url']})")
    b = CDP(t["webSocketDebuggerUrl"], timeout=10.0)
    
    b.call("Network.enable")
    b.call("Runtime.enable")
    b.call("Page.enable")
    
    # Inject Proxy Tracer into main page
    proxy_script = """
    if (!window.__tracer_installed) {
        window.__tracer_installed = true;
        const originalFetch = window.fetch;
        window.fetch = async function(...args) {
            console.log("[TRACER-FETCH]", JSON.stringify(args));
            const response = await originalFetch.apply(this, args);
            console.log("[TRACER-FETCH-RESPONSE]", response.url, response.status);
            return response;
        };
        
        const originalXHR = window.XMLHttpRequest.prototype.open;
        window.XMLHttpRequest.prototype.open = function(...args) {
            console.log("[TRACER-XHR]", JSON.stringify(args));
            return originalXHR.apply(this, args);
        };
        console.log("Tracer installed successfully.");
    }
    """
    b.call("Runtime.evaluate", {"expression": proxy_script})
    
    # Inject synthetic message and click send
    print("Typing a message to trigger PoW...")
    
    # Send a space character
    b.call("Input.insertText", {"text": " "})
    
    # Trigger Enter
    b.call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter"})
    b.call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter"})
    
    print("Listening for Network and Console events for 15 seconds...")
    end = time.monotonic() + 15.0
    
    trace_log = []
    
    while time.monotonic() < end:
        events = b.pump(0.5)
        for e in events:
            method = e.get("method")
            if method == "Network.requestWillBeSent":
                req = e.get("params", {}).get("request", {})
                url = req.get("url", "")
                if "chat.deepseek.com" in url:
                    print(f"[NET] REQ: {url}")
                    trace_log.append({"type": "request", "url": url, "method": req.get("method"), "headers": req.get("headers")})
            
            elif method == "Network.responseReceived":
                resp = e.get("params", {}).get("response", {})
                url = resp.get("url", "")
                status = resp.get("status")
                headers = resp.get("headers", {})
                if "chat.deepseek.com" in url:
                    print(f"[NET] RES: {status} {url}")
                    if "x-ds-pow-challenge" in headers or "X-Ds-Pow-Challenge" in headers:
                        print(f"!!! FOUND PoW CHALLENGE HEADER in {url} !!!")
                        print("Headers:", headers)
                    trace_log.append({"type": "response", "url": url, "status": status, "headers": headers})
            
            elif method == "Runtime.consoleAPICalled":
                args = e.get("params", {}).get("args", [])
                text_args = [a.get("value") for a in args if "value" in a]
                if text_args:
                    print("[CONSOLE]", " ".join(str(v) for v in text_args))
                    trace_log.append({"type": "console", "args": text_args})
    
    import pathlib
    out_file = pathlib.Path("state/deepseek_trace_log.json")
    out_file.write_text(json.dumps(trace_log, indent=2), encoding="utf-8")
    print(f"Trace completed. Saved to {out_file}")

if __name__ == "__main__":
    trace_pow()
