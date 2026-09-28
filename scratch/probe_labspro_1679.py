import json, pathlib, requests

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_labs_google_flow_pro.json').read_text(encoding='utf-8'))
rj = j['recorded_job']
e = rj['exchanges'][0]  # csbIsb read-only project sync
hdr = {}
for k, v in (e.get('request_headers') or {}).items():
    kl = k.lower()
    if kl.startswith(':') or kl in ('content-length', 'accept-encoding'):
        continue
    hdr[k] = v
hdr.setdefault('cookie', j.get('cookie_header', ''))
s = requests.Session()
s.headers.update(hdr)
r = s.post(e['url'], data=e.get('request_body', '').encode('utf-8'), timeout=25)
body = r.text[:300].replace('\n', ' ')
print('csbIsb replay ->', r.status_code, '|', body)
print('redirect history:', [h.status_code for h in r.history])
