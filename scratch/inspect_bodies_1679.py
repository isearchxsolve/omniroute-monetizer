import json, pathlib

d = pathlib.Path(r'D:\omniroute-monetizer\state\captures_pending')
targets = {
    'session_chatglm_cn_session_video_chatglm.json': [2],
    'session_genspark_ai_providers.json': [1],
    'session_giz_ai_p9223.json': [2, 5, 9],
    'session_labs_google_flow_pro.json': [1],
}
for fn, idxs in targets.items():
    j = json.loads((d / fn).read_text(encoding='utf-8'))
    for i in idxs:
        e = j['recorded_job']['exchanges'][i]
        body = e.get('request_body') or ''
        print('===', fn, 'exchange', i, e.get('method'), e.get('url', '')[:110])
        print('HEADERS:', json.dumps(e.get('request_headers', {}), indent=None)[:400])
        print('BODY:', body[:600].replace('\\n', ' | '))
        print()
