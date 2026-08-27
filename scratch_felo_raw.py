"""Replay Felo once and dump the RAW rejection body + response headers (secrets redacted)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts/automation"))

from universal_replay import UniversalSessionClient

p = pathlib.Path("state/secrets/session_felo_ai_web.json")
client = UniversalSessionClient(str(p))

# Monkeypatch to capture the raw response before extraction
import universal_replay as ur
orig = None
captured = {}

import requests as _rq
_orig_post = _rq.Session.request
def spy(self, method, url, **kw):
    r = _orig_post(self, method, url, **kw)
    captured["status"] = r.status_code
    captured["headers"] = dict(r.headers)
    captured["body"] = r.text[:2000]
    return r
_rq.Session.request = spy

try:
    ans = client.chat([{"role": "user", "content": "Reply with only the number: 41 + 17"}])
    print("ANSWER:", str(ans)[:300])
except Exception as e:
    print("EXC:", type(e).__name__, str(e)[:300])

print("\n--- raw ---")
print("status:", captured.get("status"))
print("body:", captured.get("body"))
print("content-type:", (captured.get("headers") or {}).get("Content-Type"))
