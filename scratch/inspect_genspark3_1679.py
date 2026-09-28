import json, pathlib, re

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_genspark_ai_providers.json').read_text(encoding='utf-8'))
e = j['recorded_job']['exchanges'][1]
rb = e.get('response_body') or ''
i = rb.find('"role": "tool"')
if i >= 0:
    print('TOOL CHUNK RAW:')
    print(rb[i:i+2200].replace('\\n', ' | ')[:2000])
print()
deltas = re.findall(r'"content": "((?:[^"\\]|\\.)*)"', rb)
big = [x for x in deltas if len(x) > 40]
print('LONG DELTAS (first 3):')
for x in big[:3]:
    print('-', x[:200])
