import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

conns = api.get_connections()
ddg = [c for c in conns if (c.get("provider") or "") == "duckduckgo-web"]
if ddg:
    cid = ddg[0]["id"]
    print("existing duckduckgo-web conn:", cid, "active:", ddg[0].get("isActive"))
else:
    print("no conn; creating")
    body = {"provider": "duckduckgo-web", "name": "duckduckgo-web", "authType": "none", "apiKey": "", "isActive": True}
    r = api.session.post(f"{api.api}/providers", json=body, timeout=30)
    print("create:", r.status_code, r.text[:200])
    cid = (r.json().get("id") or r.json().get("connection", {}).get("id")) if r.status_code in (200, 201) else None

if cid:
    t = api.test_connection(cid)
    print("test:", t.get("http_status"), json.dumps(t.get("result"))[:250])

    try:
        r = api.session.get(f"{api.api}/providers/{cid}/models", timeout=30)
        models = r.json() if r.status_code == 200 else None
        if isinstance(models, dict):
            models = models.get("models") or models.get("data") or []
        names = [m.get("id") if isinstance(m, dict) else m for m in (models or [])][:10]
        print("models:", names)
    except Exception as e:
        print("models err:", e)
        names = []

    model = f"duckduckgo-web/{names[0]}" if names else "duckduckgo-web/gpt-4o-mini"
    payload = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "max_tokens": 60, "stream": False}
    resp = api.session.post(f"{api.v1}/chat/completions", json=payload, timeout=120)
    print("E2E HTTP:", resp.status_code)
    print("body:", resp.text[:400])
    if resp.status_code == 200:
        try:
            j = resp.json()
            print("CONTENT:", repr(j["choices"][0]["message"]["content"][:200]))
        except Exception as e:
            print("parse err:", e)
