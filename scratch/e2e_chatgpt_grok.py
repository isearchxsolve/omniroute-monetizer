import sys, json, time
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

targets = {
    "chatgpt-web": "8ae51957-a156-4b57-91f1-1715984d4b81",
    "grok-web": "142fea8e-eacf-4ce3-b042-fc3af37cb36c",
}

for prov, cid in targets.items():
    print(f"\n===== {prov} ({cid}) =====")
    # test_connection
    t = api.test_connection(cid)
    print("test_connection:", t.get("http_status"), json.dumps(t.get("result"))[:200])

    # get models
    try:
        r = api.session.get(f"{api.api}/providers/{cid}/models", timeout=30)
        models = r.json() if r.status_code == 200 else None
        if isinstance(models, dict):
            models = models.get("models") or models.get("data") or []
        names = [m.get("id") if isinstance(m, dict) else m for m in (models or [])][:8]
        print("models:", names)
    except Exception as e:
        print("models error:", e)
        names = []

    # E2E with first model (prefixed)
    model = f"{prov}/{names[0]}" if names else f"{prov}/default"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 60,
        "stream": False,
    }
    try:
        r = api.session.post(f"{api.v1}/chat/completions", json=payload, timeout=90)
        print(f"E2E {model}: HTTP {r.status_code}")
        body = r.text[:400]
        print("body:", body)
        if r.status_code == 200:
            try:
                j = r.json()
                content = j["choices"][0]["message"]["content"]
                print("CONTENT:", repr(content[:200]))
            except Exception as e:
                print("parse error:", e)
    except Exception as e:
        print("E2E error:", e)
