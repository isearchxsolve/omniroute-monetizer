import urllib.request
req = urllib.request.Request('https://chat.deepseek.com/api/v0/chat/completion', method='OPTIONS', headers={'User-Agent':'Mozilla/5.0'})
try:
    res = urllib.request.urlopen(req)
    print(res.headers)
except Exception as e:
    print(e.headers)
