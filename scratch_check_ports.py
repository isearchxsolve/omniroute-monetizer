import urllib.request
import json

for port in [9222, 9223, 9224, 9225]:
    print(f"=== PORT {port} ===")
    try:
        url = f"http://127.0.0.1:{port}/json/list"
        req = urllib.request.urlopen(url, timeout=3)
        tabs = json.loads(req.read().decode('utf-8'))
        for t in tabs:
            if t.get('type') == 'page':
                print(f"  [{t.get('id')[:8]}] {t.get('title')} -> {t.get('url')}")
    except Exception as e:
        print(f"  Error: {e}")
