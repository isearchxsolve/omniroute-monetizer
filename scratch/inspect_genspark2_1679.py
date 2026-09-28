import json, pathlib, re

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_genspark_ai_providers.json').read_text(encoding='utf-8'))
e = j['recorded_job']['exchanges'][1]
rb = e.get('response_body') or ''
# message_result events: what did the video agent produce?
for m in re.finditer(r'data: (\{.*?"type": "message_result".*?)\n', rb):
    try:
        obj = json.loads(m.group(1))
        s = json.dumps(obj)
        print('RESULT:', s[:500])
        print()
    except ValueError:
        pass
# agent_notification
for m in re.finditer(r'data: (\{.*?"type": "agent_notification".*?)\n', rb):
    print('NOTIF:', m.group(1)[:300])
