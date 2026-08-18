"""Update perplexity-web connection with fresh cookies + E2E verify."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
sys.stdout.reconfigure(encoding="utf-8")

from omniroute_api import OmniRouteAPI  # noqa: E402

KEYS = os.path.join(os.path.dirname(__file__), "..", "state", "generated_keys.json")
CID = "3b45f2bf-f1aa-4162-a305-ace36bddd4b7"  # perplexity-web

with open(KEYS, "r", encoding="utf-8") as f:
    keys = json.load(f)

entry = keys.get("cookie_header:perplexity-web")
if not entry:
    print("!! no cookie_header:perplexity-web in state")
    sys.exit(1)
header = entry["cookie_header"] if isinstance(entry, dict) else entry
print(f"fresh cookie header len={len(header)}")

api = OmniRouteAPI()
api.login()

# Update the connection with the fresh cookie
r = api.update_connection(CID, {"apiKey": header})
print(f"update_connection: HTTP {r['http_status']}")

# Test connection
t = api.test_connection(CID)
print(f"test_connection: HTTP {t['http_status']}")
tj = t.get("result") or {}
print(f"  valid={tj.get('valid')} msg={str(tj.get('message') or tj.get('error'))[:120]}")

# E2E: real /v1/chat/completions with provider-prefixed model
print("\n--- E2E /v1/chat/completions ---")
for model in ["perplexity-web/pplx-sonar", "perplexity-web/pplx-auto"]:
    try:
        resp = api.session.post(
            f"{api.v1}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                "max_tokens": 60,
            },
            timeout=60,
        )
        print(f"{model}: HTTP {resp.status_code}")
        if resp.status_code == 200:
            try:
                j = resp.json()
                content = j["choices"][0]["message"]["content"]
                print(f"  [LIVE] content: {content[:100]!r}")
            except Exception as e:
                print(f"  (parse err: {e}) body={resp.text[:200]}")
        else:
            print(f"  body: {resp.text[:300]}")
    except Exception as e:
        print(f"{model}: EXC {e}")
