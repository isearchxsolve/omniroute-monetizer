"""Wave of gateway & inference providers: fenayai, thebai, venice, maritalk, publicai, predibase.
Opens tabs via PUT /json/new, checks SSO, navigates to key pages, captures keys, wires to OmniRoute, closes tabs.
"""
import sys, json, time, urllib.request, websocket

PW_URL = 'http://127.0.0.1:9222'

targets = [
    ('fenayai', 'https://fenayai.com'),
    ('thebai', 'https://theb.ai'),
    ('venice', 'https://venice.ai'),
    ('maritalk', 'https://www.maritaca.ai'),
    ('publicai', 'https://publicai.co'),
    ('predibase', 'https://predibase.com'),
]

print("[+] Opening 6 targets...")
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
        sso: Array.from(document.querySelectorAll('button, a')).map(b=>({text:b.innerText.trim(), href:b.href||''})).filter(x=>x.text.toLowerCase().includes('google') || x.text.toLowerCase().includes('sign') || x.text.toLowerCase().includes('log') || x.text.toLowerCase().includes('key') || x.text.toLowerCase().includes('start') || x.text.toLowerCase().includes('try'))
    }))()""")
    print(f"\n=== [{slug}] ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))
