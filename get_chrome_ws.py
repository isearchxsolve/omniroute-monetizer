import os
import json
import urllib.request
import urllib.error

def get_chrome_ws_url():
    local_app_data = os.environ.get('LOCALAPPDATA')
    if not local_app_data:
        return None
    user_data_dir = os.path.join(local_app_data, 'Google', 'Chrome', 'User Data')
    devtools_active_port_file = os.path.join(user_data_dir, 'DevToolsActivePort')
    
    if not os.path.exists(devtools_active_port_file):
        return None
    
    try:
        with open(devtools_active_port_file, 'r') as f:
            lines = f.read().splitlines()
            if len(lines) < 2:
                return None
            port = lines[0].strip()
            if not port.isdigit():
                return None
            # Now get the WebSocket URL from the JSON endpoint
            try:
                resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=1)
                data = json.load(resp)
                return data.get('webSocketDebuggerUrl')
            except Exception:
                return None
    except Exception:
        return None

if __name__ == "__main__":
    ws_url = get_chrome_ws_url()
    if ws_url:
        print(f"WebSocket URL: {ws_url}")
    else:
        print("Could not determine WebSocket URL")