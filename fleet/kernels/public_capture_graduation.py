"""Public GET capture graduation from real Playwright responses, never invented HARs.

Authenticated traffic is deliberately rejected: credentials must not enter KV recipes.
Only a successful independent curl result may receive the wire_verified pin.
"""

def replay_public_capture(recipe, timeout_s=25):
    import base64
    import hashlib
    import json
    import subprocess
    request = recipe.get('request') or {}
    if request.get('method') != 'GET' or recipe.get('authenticated'):
        return {'status': 'failed', 'error': 'unsupported_capture_contract'}
    cmd = ['curl', '-sS', '--location', '--max-time', str(min(timeout_s, 30)),
           '--max-filesize', '100000', '--write-out', '\n%{http_code}\t%{content_type}', request['url']]
    proc = subprocess.run(cmd, capture_output=True, timeout=min(timeout_s, 30)+5)
    raw, sep, metadata = proc.stdout.rpartition(b'\n')
    try:
        status, content_type = metadata.decode('utf-8', 'replace').split('\t', 1)
        status = int(status)
    except ValueError:
        status, content_type, raw = 0, '', proc.stdout
    sentinel = recipe.get('sentinel') or {}
    passed = proc.returncode == 0 and status == sentinel.get('expect_status') and len(raw) >= sentinel.get('min_bytes', 1)
    keys = sentinel.get('require_json_keys') or []
    if keys:
        try:
            obj = json.loads(raw)
            passed = passed and isinstance(obj, dict) and all(key in obj for key in keys)
        except (ValueError, UnicodeError):
            passed = False
    expected_type = sentinel.get('content_type')
    if expected_type:
        passed = passed and content_type.split(';')[0].strip() == expected_type
    return {'status': 'done' if passed else 'sentinel_failed', 'http_status': status or None,
            'content_type': content_type, 'content_b64': base64.b64encode(raw).decode(),
            'body_sha256': hashlib.sha256(raw).hexdigest(),
            'error': None if passed else 'independent_wire_sentinel_failed'}


def graduate_public_capture(response, capture_id, timeout_s=25):
    import hashlib
    import json
    import time
    import urllib.parse
    if not response or response.status != 200:
        raise ValueError('browser_response_not_http_200')
    request = response.request
    headers = {k.lower(): v for k, v in request.all_headers().items()}
    sensitive = {'authorization', 'cookie', 'proxy-authorization', 'x-api-key', 'api-key'}
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.url).query)
    if request.method != 'GET' or sensitive.intersection(headers) or any(
        any(s in name.lower() for s in ('token', 'secret', 'password', 'key', 'session')) for name in query
    ):
        raise ValueError('authenticated_or_non_get_capture_requires_separate_secure_contract')
    body = response.body()
    if not body or len(body) > 100000:
        raise ValueError('browser_response_size_outside_capture_contract')
    content_type = (response.headers.get('content-type') or '').split(';')[0].strip()
    if content_type != 'application/json':
        raise ValueError('public_json_response_required_for_this_graduation_contract')
    sentinel = {'expect_status': 200, 'content_type': content_type, 'min_bytes': max(1, len(body)//4)}
    if content_type == 'application/json':
        obj = json.loads(body)
        if not isinstance(obj, dict) or not obj:
            raise ValueError('json_object_required_for_public_graduation')
        if obj.get('error') or obj.get('errors') or obj.get('success') is False or obj.get('login_required'):
            raise ValueError('upstream_error_payload_cannot_graduate')
        sentinel['require_json_keys'] = list(obj)[:5]
    recipe = {'capture_id': capture_id, 'synthesized_at': int(time.time()),
              'authenticated': False, 'request': {'url': request.url, 'method': 'GET'},
              'sentinel': sentinel, 'observed_body_sha256': hashlib.sha256(body).hexdigest(),
              'execution_pin': 'playwright', 'verification': 'browser_observed'}
    proof = replay_public_capture(recipe, timeout_s)
    recipe['shadow_proof'] = {key: value for key, value in proof.items() if key not in ('content_b64',)}
    if proof['status'] == 'done':
        recipe.update(execution_pin='wire_verified', verification='shadow_curl_passed')
    return recipe
