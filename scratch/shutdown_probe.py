import sys, time
sys.path.insert(0, 'scripts/automation')
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()
print("login ok", flush=True)
try:
    r = api.session.post(f'{api.api}/shutdown', json={}, timeout=20)
    print("POST /api/shutdown ->", r.status_code, flush=True)
    print("body:", r.text[:400], flush=True)
except Exception as e:
    print("EXC:", type(e).__name__, str(e)[:300], flush=True)
