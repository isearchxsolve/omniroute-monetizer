import json, pathlib

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_chatglm_cn_session_video_chatglm.json').read_text(encoding='utf-8'))
rj = j['recorded_job']
print('cookie_header head:', j.get('cookie_header', '')[:200])
print()
for i, e in enumerate(rj['exchanges']):
    if e.get('method') == 'POST' and 'assistant/stream' in e.get('url', ''):
        print('SUBMIT HEADERS:')
        for k, v in (e.get('request_headers') or {}).items():
            if k.lower() in ('authorization',):
                print('  %s: %s...(%d chars)' % (k, v[:40], len(v)))
            else:
                print('  %s: %s' % (k, str(v)[:100]))
        break
# the guest chat_status GETs
for i, e in enumerate(rj['exchanges']):
    if 'guest/chat_status' in e.get('url', ''):
        print()
        print('chat_status[%d] headers keys: %s' % (i, sorted((e.get('request_headers') or {}).keys())))
        break
