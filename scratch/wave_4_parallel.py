"""Wave of 4 parallel providers: blackbox, agentrouter, coze, dahl.
Opens tabs via PUT /json/new, checks SSO, navigates to key pages, captures keys, wires to OmniRoute, closes tabs.
"""
import sys, json, time, urllib.request, websocket
sys.path.insert(0, r'd:\omniroute-monetizer\scripts\automation')
from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

PW_URL = 'http://127.0.0.1:9222'

# 1. Fetch current open targets
resp = urllib.request.urlopen(f'{PW_URL}/json', timeout=10)
tabs = json.loads(resp.read())
print(f"[+] Initial open targets: {len(tabs)}")

# 2. Define 4 targets
targets = [
    ('agentrouter', 'https://agentrouter.org/login'),
    ('coze', 'https://www.coze.com'),
    ('dahl', 'https://inference.dahl.global'),
    ('blackbox', 'https://app.blackbox.ai/login'),
]

# Create tabs via PUT /json/new?url
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

# Function to run JS on a tab via CDP WS
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

# Inspect initial state of all 4
for slug, tab in opened:
    ws_url = tab.get('webSocketDebuggerUrl')
    if not ws_url: continue
    res = eval_tab(ws_url, """(() => ({
        url: location.href,
        title: document.title,
        body: document.body.innerText.slice(0, 500),
        sso: Array.from(document.querySelectorAll('button, a')).map(b=>b.innerText.trim()).filter(t=>t.toLowerCase().includes('google') || t.toLowerCase().includes('sign in') || t.toLowerCase().includes('login') || t.toLowerCase().includes('git'))
    }))()""")
    print(f"\n=== [{slug}] ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))
