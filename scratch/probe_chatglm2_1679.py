import json, pathlib, requests

CAP = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending\session_chatglm_cn_session_video_chatglm.json')
j = json.loads(CAP.read_text(encoding='utf-8'))
rj = j['recorded_job']
hdr = {}
rec_url = None
for e in rj['exchanges']:
    if 'guest/chat_status' in e.get('url', ''):
        rec_url = e['url']
        for k, v in (e.get('request_headers') or {}).items():
            kl = k.lower()
            if kl.startswith(':') or kl in ('content-length', 'accept-encoding'):
                continue
            hdr[k] = v
        break

s = requests.Session()
s.headers.update(hdr)
r = s.get(rec_url, timeout=15)
print('REPLAY chat_status ->', r.status_code, '|', r.text[:200].replace('\n', ' '))

for url in [
    'https://chatglm.cn/chatglm/mainchat-api/guest/auth',
    'https://chatglm.cn/chatglm/mainchat-api/guest/login',
    'https://chatglm.cn/chatglm/mainchat-api/guest/register',
    'https://chatglm.cn/chatglm/backend-api/user/refresh',
    'https://chatglm.cn/chatglm/mainchat-api/user/refresh',
]:
    try:
        rr = s.post(url, json={}, timeout=15)
        print('POST %s -> %d | %s' % (url, rr.status_code, rr.text[:160].replace('\n', ' ')))
    except requests.RequestException as ex:
        print('POST %s -> EXC %s' % (url, str(ex)[:100]))
