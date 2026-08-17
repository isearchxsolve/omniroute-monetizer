import json, urllib.request
tabs = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=5))
for t in tabs:
    if t.get('type') == 'page':
        print(t.get('url'), '|', t.get('title'))
