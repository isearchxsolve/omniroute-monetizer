import json
import urllib.request
import websocket
import time

CDP_BASE = "http://127.0.0.1:9222"

def main():
    print(f"[*] Fetching tabs from {CDP_BASE}/json/list ...")
    try:
        raw = urllib.request.urlopen(f"{CDP_BASE}/json/list", timeout=5).read()
        tabs = json.loads(raw)
    except Exception as e:
        print(f"[-] Failed to fetch tabs: {e}")
        return

    page_tabs = [t for t in tabs if t.get("type") == "page" and not t.get("url", "").startswith("chrome://")]
    print(f"[*] Found {len(page_tabs)} page tabs.")

    auth_indicators = ["log in", "sign in", "sign up", "get started", "create account"]
    
    for tab in page_tabs:
        url = tab.get("url", "")
        ws_url = tab.get("webSocketDebuggerUrl")
        title = tab.get("title", "")
        if not ws_url: continue
        
        ws_url = ws_url.replace("localhost", "127.0.0.1")
        
        try:
            ws = websocket.create_connection(ws_url, timeout=2)
            
            # Check URL for obvious login redirects
            if "login" in url.lower() or "signin" in url.lower() or "auth" in url.lower():
                print(f"  [LOGGED OUT?] {url[:60]:<60} (Redirected to auth URL)")
                ws.close()
                continue
            
            # Evaluate document text
            eval_cmd = {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": "document.body ? document.body.innerText.substring(0, 5000).toLowerCase() : ''",
                    "returnByValue": True
                }
            }
            ws.send(json.dumps(eval_cmd))
            result = json.loads(ws.recv())
            ws.close()
            
            if "result" in result and "result" in result["result"]:
                text = result["result"]["result"].get("value", "")
                
                # Check for indicators in the text
                is_logged_out = False
                for indicator in auth_indicators:
                    if f"\\n{indicator}\\n" in text or f" {indicator} " in text or text.startswith(indicator):
                        is_logged_out = True
                        break
                
                if is_logged_out:
                    print(f"  [NEEDS AUTH]  {url[:60]:<60} (Found login keywords)")
                else:
                    print(f"  [SIGNED IN]   {url[:60]:<60}")
            else:
                print(f"  [UNKNOWN]     {url[:60]:<60} (Could not read body)")
                
        except Exception as e:
            print(f"  [ERROR]       {url[:60]:<60} ({str(e)})")

if __name__ == "__main__":
    main()
