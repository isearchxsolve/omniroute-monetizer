import json, pathlib, re

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_genspark_ai_providers.json').read_text(encoding='utf-8'))
e = j['recorded_job']['exchanges'][1]
rb = e.get('response_body') or ''
# where does the capture end? last 3 events
events = [x for x in rb.split('\n') if x.startswith('data: ')]
print('total events:', len(events))
for x in events[-3:]:
    print(x[:300])
    print()
# does any event mention generate_videos execution or a wall?
low = rb.lower()
for w in ('insufficient', 'agent_credits', 'paid_plan', 'pricing', 'free_plan'):
    i = low.find(w)
    if i >= 0:
        print('WALL-WORD %r: ...%s...' % (w, rb[max(0, i-100):i+100].replace(chr(10), ' ')))
