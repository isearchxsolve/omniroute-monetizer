import json, pathlib

d = json.loads(pathlib.Path('state/free_llm_chat_sites.json').read_text(encoding='utf-8'))
lines = []
for g in d:
    for s in g.get('sites') or []:
        lines.append(f"{s.get('name')} -> {s.get('url')}")
pathlib.Path('_sites_dump.txt').write_text('\n'.join(lines), encoding='utf-8')

r = json.loads(pathlib.Path('state/replay_check.json').read_text(encoding='utf-8'))
pathlib.Path('_replay_dump.txt').write_text(json.dumps(r, indent=1), encoding='utf-8')
print('OK', len(lines), 'sites')
