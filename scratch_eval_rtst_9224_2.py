import json, urllib.request, websocket

req = urllib.request.urlopen("http://127.0.0.1:9224/json/list")
tabs = json.loads(req.read().decode('utf-8'))
for t in tabs:
    if 'rtst' in t.get('url', ''):
        ws = websocket.create_connection(t['webSocketDebuggerUrl'])
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "localStorage.getItem('auth_token')"}}))
        msg = ws.recv()
        print("rtst token on 9224:", msg)
        ws.close()
