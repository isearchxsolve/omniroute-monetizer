import json, pathlib, urllib.parse

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_labs_google_flow_pro.json').read_text(encoding='utf-8'))
rj = j['recorded_job']
for i, e in enumerate(rj['exchanges']):
    body = e.get('request_body') or ''
    url = e.get('url', '')
    q = urllib.parse.urlparse(url).query
    rpc = urllib.parse.parse_qs(q).get('rpcids', ['?'])[0]
    print('[%d] rpcid=%s len=%d' % (i, rpc, len(body)))
    if body.startswith('f.req='):
        inner = urllib.parse.unquote(body[6:])
        print('    inner head:', inner[:260].replace('\n', ' '))
    else:
        print('    body head:', body[:200].replace('\n', ' '))
    hdr = e.get('request_headers') or {}
    auth = hdr.get('Authorization') or hdr.get('authorization')
    print('    auth:', (auth[:30] + '...') if auth else None, '| cookie:', ('cookie' in [k.lower() for k in hdr]))
    print()
