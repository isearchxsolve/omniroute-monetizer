"""t3-web E2E re-verify with provider-prefixed model names."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
sys.stdout.reconfigure(encoding="utf-8")
from omniroute_api import OmniRouteAPI  # noqa: E402

CID = "ef5082c2-e57e-4a6d-8e99-0e0cad698fbd"  # t3-web

api = OmniRouteAPI()
api.login()

# get models
mr = api.session.get(f"{api.api}/providers/{CID}/models", timeout=30)
models = []
if mr.status_code == 200:
    try:
        mj = mr.json()
        mlist = mj.get("models") if isinstance(mj, dict) else mj
        for m in (mlist or []):
            mid = m.get("id") if isinstance(m, dict) else str(m)
            if mid:
                models.append(mid)
    except Exception:
        pass
print(f"t3-web models ({len(models)}): {models[:12]}")

print("\n--- E2E /v1/chat/completions (prefixed) ---")
# pick a few representative models
targets = [f"t3-web/{m}" for m in models[:3]] if models else ["t3-web/gpt-4o"]
for model in targets:
    try:
        resp = api.session.post(
            f"{api.v1}/chat/completions",
            json={"model": model,
                  "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                  "max_tokens": 60},
            timeout=90,
        )
        print(f"\n{model}: HTTP {resp.status_code}")
        txt = resp.text
        if resp.status_code == 200:
            if txt.lstrip().startswith("data:"):
                content = ""
                for line in txt.splitlines():
                    line = line.strip()
                    if line.startswith("data:") and "[DONE]" not in line:
                        try:
                            j = json.loads(line[5:].strip())
                            d = j.get("choices", [{}])[0].get("delta", {})
                            content += d.get("content") or ""
                        except Exception:
                            pass
                print(f"  [LIVE-SSE] content: {content[:120]!r}")
            else:
                try:
                    j = resp.json()
                    print(f"  [LIVE] content: {j['choices'][0]['message']['content'][:120]!r}")
                except Exception:
                    print(f"  body: {txt[:200]}")
        else:
            print(f"  body: {txt[:300]}")
    except Exception as e:
        print(f"{model}: EXC {type(e).__name__}: {e}")
