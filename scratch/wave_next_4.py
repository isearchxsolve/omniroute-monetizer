"""Wave of 4 parallel providers: 360ai, dify, hcnsec, clarifai.
Opens tabs via PUT /json/new, checks SSO, navigates to key pages, captures keys, wires to OmniRoute, closes tabs.
"""
import sys, json, time, urllib.request, websocket

PW_URL = 'http://127.0.0.1:9222'

targets = [
    ('360ai', 'https://ai.360.cn'),
    ('dify', 'https://dify.ai'),
    ('hcnsec', 'https://api.hcnsec.cn'),
    ('clarifai', 'https://clarifai.com/login'),
]

print("[+] Opening 4 targets...")
opened = []
for slug, url in targets:
    try:
        req = urllib.request.Request(f"{PW_URL}/json/new?{url}", method='PUT')
        resp = urllib.request.urlopen(req, timeout=10)
        tab_info = json.loads(resp.read())
        opened.append((slug, tab_info))
        print(f"  [{slug}] opened tab {tab_info['id'][:8]} -> {url}")
    except Exception as e:
        print(f"  [{slug}] failed to open: {e}")

time.sleep(4)

def eval_tab(tab_ws_url, js):
    try:
        ws = websocket.create_connection(tab_ws_url, timeout=10, suppress_origin=True)
        req = {'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': js, 'returnByValue': True}}
        ws.send(json.dumps(req))
        resp = ws.recv()
        ws.close()
        return json.loads(resp).get('result', {}).get('result', {}).get('value')
    except Exception as e:
        return {'error': str(e)}

for slug, tab in opened:
    ws_url = tab.get('webSocketDebuggerUrl')
    if not ws_url: continue
    res = eval_tab(ws_url, """(() => ({
        url: location.href,
        title: document.title,
        body: document.body.innerText.slice(0, 500),
        sso: Array.from(document.querySelectorAll('button, a')).map(b=>b.innerText.trim()).filter(t=>t.toLowerCase().includes('google') || t.toLowerCase().includes('sign') || t.toLowerCase().includes('log') || t.toLowerCase().includes('key'))
    }))()""")
    print(f"\n=== [{slug}] ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))
