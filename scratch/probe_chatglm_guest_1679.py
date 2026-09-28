import json, pathlib, requests

CAP = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending\session_chatglm_cn_session_video_chatglm.json')
j = json.loads(CAP.read_text(encoding='utf-8'))
rj = j['recorded_job']
# pull a clean header set from the recorded chat_status GET (no pseudo-headers, no content-length)
hdr = {}
for e in rj['exchanges']:
    if 'guest/chat_status' in e.get('url', ''):
        for k, v in (e.get('request_headers') or {}).items():
            kl = k.lower()
            if kl.startswith(':') or kl in ('content-length', 'accept-encoding', 'cookie'):
                continue
            hdr[k] = v
        break
hdr['accept-encoding'] = 'gzip, deflate'

s = requests.Session()
s.headers.update(hdr)
candidates = [
    ('POST', 'https://chatglm.cn/chatglm/backend-api/user/guest/auth'),
    ('POST', 'https://chatglm.cn/chatglm/mainchat-api/user/guest/auth'),
    ('GET',  'https://chatglm.cn/chatglm/backend-api/user/guest/auth'),
    ('POST', 'https://chatglm.cn/chatglm/backend-api/user/guest'),
    ('POST', 'https://chatglm.cn/backend-api/user/guest/auth'),
    ('GET',  'https://chatglm.cn/chatglm/backend-api/user/chat_status'),
]
for method, url in candidates:
    try:
        r = s.request(method, url, json={} if method == 'POST' else None, timeout=15)
        body = r.text[:220].replace('\n', ' ')
        print('%s %s -> %d | %s' % (method, url, r.status_code, body))
    except requests.RequestException as ex:
        print('%s %s -> EXC %s' % (method, url, str(ex)[:120]))
