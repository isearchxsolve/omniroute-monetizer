"""Read-only current checks for admitted video seats. No submits or browser attach."""
import concurrent.futures, datetime, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/automation'))
from pure_python_registry import load_registry

OUT = ROOT / 'state/graduated_video_preflight_20261017.json'
entries = [e for e in load_registry()['entries'] if e.get('state') == 'ADMITTED' and e.get('modality') == 'video']
report = {'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope': 'read-only current checks; historical admission is not a fresh render receipt',
          'seats': []}

def check(entry):
    row = {key: entry.get(key) for key in ['sessionFile', 'host', 'adapter', 'verifiedAt']}
    try:
        secret = ROOT / 'state/secrets' / entry['sessionFile']
        if entry['adapter'].startswith('chrome:'):
            row.update(status='requires_owned_browser_executor', render_verified_now=False)
        elif entry['adapter'].startswith('api:digen'):
            from video_provider_digen import DigenProvider
            import requests
            client = DigenProvider()
            client._load_session()
            response = requests.get('https://api.digen.ai/v1/credit/remain', headers=client._headers, timeout=15)
            row['http_status'] = response.status_code
            response.raise_for_status()
            payload = response.json()
            data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
            fields = [key for key in ('remained', 'premiumRemained') if key in data]
            if payload.get('errCode') != 0 or not fields:
                # Observed live schema 2026-10-17: data.remained + data.premiumRemained.
                # An absent field is a schema fact, never a verified zero balance.
                raise ValueError(
                    'Balance response did not expose data.remained/premiumRemained '
                    f'(errCode={payload.get("errCode")!r}, dataKeys={sorted(data)[:8]})')
            row.update(status='balance_read_verified',
                       credits_remained=data.get('remained'),
                       credits_premium_remained=data.get('premiumRemained'),
                       credits=sum(int(data[key]) for key in fields),
                       render_verified_now=False)
        elif entry['adapter'] == 'api:rtst':
            from rtst_api_client import RtstApiClient
            client = RtstApiClient(secret=secret, timeout=20)
            balance = client._call('/user/credits')
            if 'credits' not in balance:
                raise ValueError('Balance response omitted credits')
            models = client.models()
            row.update(status='balance_and_menu_read_verified', credits=balance['credits'],
                       video_model_count=len(models), render_verified_now=False)
        elif entry['adapter'] == 'api:hf_ltx_space':
            from gradio_space_client import GradioSpaceClient
            info = GradioSpaceClient('https://lightricks-ltx-video-distilled.hf.space', timeout=25).info()
            names = info.get('named_endpoints') or {}
            endpoint = names.get('/text_to_video') or names.get('text_to_video')
            row.update(status='public_endpoint_read_verified' if endpoint else 'endpoint_contract_changed',
                       text_to_video_present=bool(endpoint),
                       parameter_names=[p.get('parameter_name') for p in (endpoint or {}).get('parameters', [])],
                       render_verified_now=False)
        else:
            row.update(status='adapter_not_checked', render_verified_now=False)
    except Exception as error:
        row.update(status='current_read_failed', error_type=type(error).__name__,
                   error_code=getattr(error, 'code', None) or (error.args[0] if error.args and error.args[0] in ['AUTH', 'NO_TOKEN', 'NO_SESSION', 'NO_RECORDING', 'NO_HEADERS'] else None),
                   http_status=getattr(error, 'status', None) or row.get('http_status'),
                   render_verified_now=False)
    return row

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    for future in concurrent.futures.as_completed([executor.submit(check, entry) for entry in entries]):
        row = future.result()
        report['seats'].append(row)
        OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(row), flush=True)
print('AUTHENTIC_CURRENT_READ_RECEIPT', str(OUT), flush=True)
