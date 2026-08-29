import json
import urllib.request
import time
import pathlib
import websocket
from urllib.parse import urlparse

SECRETS_DIR = pathlib.Path("state/secrets")

def main():
    if not SECRETS_DIR.exists():
        print("No secrets directory found.")
        return

    # 1. Gather all cookies from session files
    domain_cookies = {}
    for sf in SECRETS_DIR.glob("session_*.json"):
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            host = data.get("host")
            cookie_header = data.get("cookie_header")
            if not host or not cookie_header: continue
            
            cookies = []
            for pair in cookie_header.split(";"):
                pair = pair.strip()
                if not pair: continue
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    domain = host if host.startswith(".") else "." + host
                    cookies.append({
                        "name": k.strip(),
                        "value": v.strip(),
                        "domain": domain,
                        "path": "/"
                    })
            
            if cookies:
                domain_cookies[host] = cookies
        except Exception as e:
            pass

    print(f"[*] Loaded cookies for {len(domain_cookies)} domains.")

    # 2. Get tabs from Chrome
    print("[*] Fetching tabs from http://127.0.0.1:9222/json/list ...")
    try:
        raw = urllib.request.urlopen("http://localhost:9222/json/list", timeout=5).read()
        tabs = json.loads(raw)
    except Exception as e:
        print(f"[-] Failed to fetch tabs: {e}")
        return

    print(f"[*] Found {len(tabs)} open tabs.")

    restored_count = 0
    # Process tabs that match our cookies
    for tab in tabs:
        url = tab.get("url", "")
        ws_url = tab.get("webSocketDebuggerUrl")
        
        if not url or not ws_url or url.startswith("chrome://"):
            continue
            
        domain = urlparse(url).netloc
        matched_host = None
        for host in domain_cookies.keys():
            if host in domain or domain in host:
                matched_host = host
                break
                
        if matched_host:
            cookies_to_add = domain_cookies[matched_host]
            # Force IPv4 to avoid websocket-client IPv6 timeout issue
            ws_url = ws_url.replace("localhost", "127.0.0.1")
            print(f"  -> Restoring {matched_host} cookies via {ws_url}")
            try:
                ws = websocket.create_connection(ws_url, timeout=1)
                # Set the cookies
                cmd = {
                    "id": 1,
                    "method": "Network.setCookies",
                    "params": {"cookies": cookies_to_add}
                }
                ws.send(json.dumps(cmd))
                
                # Reload the page to apply the cookies and return to chat interface
                reload_cmd = {
                    "id": 2,
                    "method": "Page.reload"
                }
                ws.send(json.dumps(reload_cmd))
                ws.close()
                
                # Sleep to prevent crashing Chrome by reloading too many heavy tabs simultaneously
                time.sleep(2.0)
                restored_count += 1
            except Exception as e:
                print(f"     [-] WS error on tab {url[:40]}: {e}")

    print(f"\n[+] Fast WS cookie restoration complete! Restored and reloaded {restored_count} tabs.")

if __name__ == "__main__":
    main()
