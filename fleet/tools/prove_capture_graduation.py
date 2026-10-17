"""Verify real cold browser graduation and warm curl replay; never seed results."""
import base64, hashlib, json, pathlib, time
from door_client import request

OUT = pathlib.Path(__file__).resolve().parents[2] / 'state/film_support_graduation_20261017.json'
CID = 'github.cpython.metadata.20261017.v1'
data = json.loads(OUT.read_text())

def save():
    OUT.write_text(json.dumps(data, indent=2), encoding='utf-8')

def finish(label, submission, executor):
    for _ in range(28):
        result = request('/v1/tools/web.result', params={'job_id': submission['job_id']})
        data[label] = result
        save()
        print(label, result.get('status'), flush=True)
        if result.get('status') in ('done', 'failed'):
            body = base64.b64decode(result.get('content_b64', ''))
            payload = json.loads(body)
            if executor == 'kaggle:playwright':
                # Browser executor returns its documented DOM envelope, not raw HTTP bytes.
                target_verified = (payload.get('final_url') == 'https://api.github.com/repos/python/cpython'
                                   and '"full_name": "python/cpython"' in payload.get('text', '')
                                   and result.get('graduated_capture', {}).get('verification') == 'shadow_curl_passed')
            else:
                target_verified = payload.get('full_name') == 'python/cpython'
            verified = (result.get('status') == 'done' and result.get('http_status') == 200
                        and result.get('executed_by') == executor and target_verified)
            data[label + '_proof'] = {'verified': verified, 'body_sha256': hashlib.sha256(body).hexdigest()}
            save()
            if not verified:
                raise RuntimeError(label + ' did not earn live proof')
            return
        time.sleep(15)
    raise TimeoutError(label + ' still pending; receipt preserved')

finish('cold_response', data['cold_submission'], 'kaggle:playwright')
data['capture_status'] = request('/v1/captures/status', params={'capture_id': CID})
save()
if data['capture_status'].get('execution_pin') != 'wire_verified':
    raise RuntimeError('Capture did not graduate')
if 'warm_submission' not in data:
    data['warm_submission'] = request('/v1/tools/web.execute', {'capture_id': CID, 'timeout_s': 30})
    save()
finish('warm_response', data['warm_submission'], 'kaggle:cloud-cell')
data['all_verified'] = True
save()
print('LIVE_BROWSER_AND_CURL_VERIFIED', str(OUT), flush=True)
