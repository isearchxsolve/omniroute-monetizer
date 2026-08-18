"""Lightweight direct-CDP evaluator and wire tool.
Connects directly to target WebSocket URL, evaluates JS, extracts keys, wires to OmniRoute, closes tab.
"""
import sys, json, urllib.request, time
import websocket

def evaluate_cdp(ws_url, expression):
    ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
    req = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "returnByValue": True
        }
    }
    ws.send(json.dumps(req))
    resp = ws.recv()
    ws.close()
    data = json.loads(resp)
    result = data.get("result", {}).get("result", {}).get("value")
    return result

def close_tab(tab_id):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{tab_id}", timeout=5)
        print(f"[+] Tab {tab_id} closed")
    except Exception as e:
        print(f"[-] Failed to close tab {tab_id}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: cdp_eval.py <ws_url> <js_expr>")
        sys.exit(1)
    ws_url = sys.argv[1]
    js = sys.argv[2]
    res = evaluate_cdp(ws_url, js)
    print(json.dumps(res, indent=2, ensure_ascii=False))
