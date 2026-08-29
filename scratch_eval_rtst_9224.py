import json, websocket, urllib.request

req = urllib.request.urlopen("http://127.0.0.1:9224/json/list")
tabs = json.loads(req.read().decode('utf-8'))
ws_url = None
for t in tabs:
    if 'rtst.ai' in t.get('url', ''):
        ws_url = t.get('webSocketDebuggerUrl')
        break

if ws_url:
    ws = websocket.create_connection(ws_url)
    ws.send(json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": "JSON.stringify({url: window.location.href, token: localStorage.getItem('auth_token'), bodyText: document.body.innerText.slice(0, 300)})"
        }
    }))
    res = json.loads(ws.recv())
    print(res.get('result', {}).get('value'))
    ws.close()
