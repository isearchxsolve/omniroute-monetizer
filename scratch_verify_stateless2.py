import json, urllib.request, time

body = json.dumps({
    'model': 'video/auto',
    'messages': [{'role': 'user', 'content':
        'A slow cinematic pan across a neon-lit alley at night, rain reflections on wet pavement, soft volumetric fog, 5 seconds.'}],
    'video': {'job_key': 'verify-stateless-longprompt-' + str(int(time.time()))}
}).encode()
req = urllib.request.Request('http://127.0.0.1:8190/v1/chat/completions', data=body, method='POST')
req.add_header('Content-Type', 'application/json')
r = urllib.request.urlopen(req, timeout=30)
rec = json.loads(r.read())
print('submit status:', r.status)
jid = (rec.get('video') or {}).get('jobId')
print('job_id:', jid)

final = None
for i in range(20):
    time.sleep(4)
    d = json.load(urllib.request.urlopen('http://127.0.0.1:8190/v1/video/jobs/' + jid, timeout=10))
    v = d.get('video') or {}
    st = v.get('status')
    prov = v.get('provider')
    sess = v.get('session')
    print('  t+%ds status=%s provider=%s session=%s' % ((i + 1) * 4, st, prov, sess))
    if st in ('succeeded', 'failed', 'cancelled'):
        final = v
        print('  url:', (v.get('url') or '')[:100])
        print('  error:', v.get('error'))
        break

d = json.load(urllib.request.urlopen('http://127.0.0.1:8190/v1/video/jobs/' + jid, timeout=10))
print('ATTEMPT HISTORY:')
for a in (d.get('attempts') or []):
    print('  ', a.get('host'), '|', a.get('session'), '|', (a.get('error') or 'OK')[:90])
