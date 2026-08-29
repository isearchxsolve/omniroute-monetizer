import urllib.request, json

req = urllib.request.urlopen("http://127.0.0.1:9224/json/list")
tabs = json.loads(req.read().decode('utf-8'))
for t in tabs:
    print(t.get('title'), t.get('url'))
