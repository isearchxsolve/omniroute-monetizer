import json, pathlib

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
SENT = 'Reply exactly one word: Omni.'
for f in sorted(d.glob('session_*.json')):
    if 'digen' in f.name:
        continue
    j = json.loads(f.read_text(encoding='utf-8'))
    rj = j['recorded_job']
    print('===', f.name)
    print(' recorded_at:', rj.get('recorded_at'))
    print(' sentinel_ok:', rj.get('sentinel') == SENT,
          '| result_seen:', rj.get('result_seen'),
          '| result_correlated:', rj.get('result_correlated'),
          '| job_id_count:', rj.get('job_id_count'),
          '| submit_seq:', rj.get('submit_seq'))
    print(' api_substr:', rj.get('api_substr'))
    for i, e in enumerate(rj['exchanges']):
        body = e.get('request_body') or ''
        # accept both the canonical sentinel and any 'Omni.' occurrence
        has_sent = (SENT in body) or ('Omni.' in body)
        if has_sent or 'Omni' in body:
            url = e.get('url', '')[:110]
            print('  [%d] %s %s body_len=%d omni_in_body=%s sentinel_exact=%s'
                  % (i, e.get('method'), url, len(body), 'Omni' in body, has_sent))
    print()
