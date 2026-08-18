import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

CID = "8ae51957-a156-4b57-91f1-1715984d4b81"  # chatgpt-web
models = ["chatgpt-web/gpt-5.5", "chatgpt-web/gpt-5.6-thinking", "chatgpt-web/o3"]

for model in models:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 60,
        "stream": False,
    }
    try:
        resp = api.session.post(f"{api.v1}/chat/completions", json=payload, timeout=120)
        if resp.status_code == 200:
            j = resp.json()
            content = j["choices"][0]["message"]["content"]
            usage = j.get("usage", {})
            print(f"{model}: HTTP 200 CONTENT={content!r} usage={usage}")
        else:
            print(f"{model}: HTTP {resp.status_code} {resp.text[:150]}")
    except Exception as e:
        print(f"{model}: EXC {type(e).__name__}: {e}")
