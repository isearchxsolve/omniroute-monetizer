import json, pathlib, re

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_giz_ai_p9223.json').read_text(encoding='utf-8'))
exs = j['recorded_job']['exchanges']
for i in (2, 9):
    e = exs[i]
    rb = e.get('response_body') or ''
    print('=== exchange [%d] %s status=%s mime=%s resp_len=%d' % (
        i, e.get('url', '')[-60:], e.get('status'), e.get('mimeType'), len(rb)))
    print('RESP HEAD:', rb[:400].replace('\n', ' | '))
    print()
# also the PUT assistantMessages responses (what did the assistant write?)
for i, e in enumerate(exs):
    if e.get('method') in ('PUT', 'PATCH') or 'assistantSessions(' in e.get('url', ''):
        rb = e.get('response_body') or ''
        if rb:
            print('[%d] %s %s -> %s | %s' % (i, e.get('method'), e.get('url', '')[-70:], e.get('status'), rb[:220].replace('\n', ' | ')))
