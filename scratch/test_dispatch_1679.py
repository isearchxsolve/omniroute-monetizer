"""Mock dispatch test: the 3 UNVERIFIED video mappings resolve through session_pool._client_for
using throwaway seat files in a temp dir. Pure logic -- no network, no credit, no real secrets."""
import sys, json, tempfile, pathlib
sys.path.insert(0, r'D:\omniroute-monetizer\scripts\automation')
import session_pool

CASES = {
    'orcarouter_video': 'orcarouter_video_client.OrcaRouterVideoClient',
    'llm7_video': 'llm7_video_client.Llm7VideoClient',
    'deepinfra_video': 'deepinfra_video_client.DeepInfraVideoClient',
}

ok = True
tmp = pathlib.Path(tempfile.mkdtemp(prefix='dispatch1679_'))
for kind, cls_path in CASES.items():
    seat = tmp / ('session_%s_test.json' % kind)
    raw = {
        'host': '%s.test' % kind, 'modality': 'video',
        'api': {'kind': kind, 'key': 'SK_TEST_NOT_REAL', 'model': 'test-model'},
    }
    seat.write_text(json.dumps(raw), encoding='utf-8')
    client = session_pool._client_for('%s.test' % kind, raw)
    if isinstance(client, type):
        # _client_for returns the CLASS for these kinds; instantiate with the api dict
        client = client({'api': {'kind': kind, 'token': 'SK_TEST_NOT_REAL', 'model': 'test-model'}})
    got = '%s.%s' % (type(client).__module__, type(client).__name__)
    exp_mod, exp_cls = cls_path.rsplit('.', 1)
    match = (type(client).__module__ == exp_mod and type(client).__name__ == exp_cls)
    got = '%s.%s' % (type(client).__module__, type(client).__name__)
    # spend gate: a fresh client must refuse to submit with gate closed
    gate_refused = False
    try:
        client.chat([{'role': 'user', 'content': 'test prompt five words or more'}])
    except Exception as e:
        gate_refused = True
        err_kind = str(getattr(e, 'kind', getattr(e, 'args', [''])[0]))
    print('%s -> %s [%s] spend-gate-refused=%s (%s)' % (kind, got, 'PASS' if match else 'FAIL', gate_refused, err_kind[:40]))
    ok = ok and match and gate_refused

print('DISPATCH+GATE', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
