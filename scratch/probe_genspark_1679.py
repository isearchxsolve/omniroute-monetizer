import json, pathlib, requests

sp = pathlib.Path(r'D:\omniroute-monetizer\state')
# old sweep verdict for genspark
rc = json.loads((sp / 'replay_check.json').read_text(encoding='utf-8'))
rows = rc.get('results') or rc.get('checks') or []
if isinstance(rc, dict) and not rows:
    for k, v in rc.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and 'verdict' in v[0]:
            rows = v
            break
for r in rows:
    if 'genspark' in str(r.get('file', '')):
        print('OLD SWEEP:', json.dumps(r)[:300])

# pending capture free-read aliveness probe (recorded bookmark GET, one request)
d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_genspark_ai_providers.json').read_text(encoding='utf-8'))
rj = j['recorded_job']
for e in rj['exchanges']:
    if 'project_bookmark' in e.get('url', ''):
        hdr = {}
        for k, v in (e.get('request_headers') or {}).items():
            kl = k.lower()
            if kl.startswith(':') or kl in ('content-length', 'accept-encoding'):
                continue
            hdr[k] = v
        hdr.setdefault('cookie', j.get('cookie_header', ''))
        s = requests.Session()
        s.headers.update(hdr)
        r = s.get(e['url'], timeout=20)
        print('bookmark replay ->', r.status_code, '|', r.text[:200].replace('\n', ' '))
        break
