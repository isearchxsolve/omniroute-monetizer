import json, pathlib, re

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
j = json.loads((d / 'session_genspark_ai_providers.json').read_text(encoding='utf-8'))
e = j['recorded_job']['exchanges'][1]
rb = e.get('response_body') or ''
# event types seen
types = re.findall(r'"type"\s*:\s*"([^"]+)"', rb)
from collections import Counter
print('event types:', Counter(types))
# look for wall language
low = rb.lower()
for w in ('credit', 'upgrade', 'quota', 'limit', 'sign in', 'login', 'premium', 'subscription'):
    if w in low:
        i = low.find(w)
        print('WALL-WORD %r at ctx: ...%s...' % (w, rb[max(0, i-80):i+80].replace(chr(10), ' ')))
# any video/url result
for m in re.finditer(r'https?://[^\s"\\]+', rb):
    u = m.group(0)
    if any(x in u for x in ('.mp4', 'video', 'storage', 'cdn')):
        print('URL:', u[:140])
