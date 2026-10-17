"""Read-only film release evidence. Never renders, charges, or logs credentials."""
import datetime, json, pathlib
from door_client import request

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = pathlib.Path(r'D:\god_ai\oioi\oioi')
config = {}
for file in (APP / '.env', APP / 'backend/.env'):
    if file.exists():
        for line in file.read_text(encoding='utf-8', errors='replace').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('\"\'')

evidence = {'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope': 'read-only; no render submission or payment transaction',
            'film_source': str(APP), 'network': {}}
for key, path in [('door', '/health'), ('gateway', '/v1/gateway'),
                  ('models', '/v1/models'), ('video_capacity', '/v1/video/capacity')]:
    try:
        evidence['network'][key] = request(path)
    except Exception as error:
        evidence['network'][key] = {'probe_error': type(error).__name__}

models = evidence['network']['models'].get('data', [])
capacity = evidence['network']['video_capacity']
database = config.get('DATABASE_URL', '')
gates = {
    'film_gateway_registered': any(s.get('service') == 'oiioii' for s in evidence['network']['gateway'].get('sessions', [])),
    'live_chat_catalogue': bool(models) and any(str(m.get('id', '')).startswith('session-pool/') for m in models),
    'live_video_capacity': isinstance(capacity.get('totalClipsAvailable'), (int, float)) and capacity['totalClipsAvailable'] > 0,
    'owner_configuration_present_locally': bool(config.get('OIOI_OWNER_EMAIL') and config.get('OIOI_OWNER_INITIAL_PASSWORD')),
    'external_database_configured': database.startswith(('postgres://', 'postgresql://', 'postgresql+asyncpg://')),
}
evidence['gates'] = gates
evidence['unverified_release_requirements'] = [
    'fresh real film render through the customer workflow',
    'authorized downloadable MP4 verified by media probe and SHA256',
    'customer/account/artifact persistence across a Kaggle session restart',
    'payment collection and customer entitlement workflow',
]
evidence['ready_for_paid_release'] = False
evidence['blockers'] = [name for name, passed in gates.items() if not passed] + evidence['unverified_release_requirements']
out = ROOT / 'state/film_product_preflight_20261017.json'
out.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
print(json.dumps({'gates': gates, 'ready_for_paid_release': False, 'receipt': str(out)}, indent=2))
