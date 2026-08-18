"""Try Perplexity search-mode models (non-copilot) to see if any return content."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
sys.stdout.reconfigure(encoding="utf-8")
from omniroute_api import OmniRouteAPI  # noqa: E402

api = OmniRouteAPI()
api.login()

# search-mode models from MODEL_MAP (protocol.ts)
targets = ["perplexity-web/pplx-glm", "perplexity-web/pplx-kimi",
           "perplexity-web/pplx-nemotron", "perplexity-web/pplx-gpt-5.6-terra"]
for model in targets:
    try:
        resp = api.session.post(
            f"{api.v1}/chat/completions",
            json={"model": model,
                  "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                  "max_tokens": 60},
            timeout=90,
        )
        txt = resp.text
        content = ""
        if resp.status_code == 200:
            if txt.lstrip().startswith("data:"):
                for line in txt.splitlines():
                    line = line.strip()
                    if line.startswith("data:") and "[DONE]" not in line:
                        try:
                            j = json.loads(line[5:].strip())
                            d = j.get("choices", [{}])[0].get("delta", {})
                            content += d.get("content") or ""
                        except Exception:
                            pass
            else:
                try:
                    content = resp.json()["choices"][0]["message"]["content"]
                except Exception:
                    pass
        status = "LIVE" if content.strip() else "EMPTY"
        print(f"{model}: HTTP {resp.status_code} [{status}] content={content[:100]!r}")
        if not content.strip() and resp.status_code != 200:
            print(f"   body: {txt[:200]}")
    except Exception as e:
        print(f"{model}: EXC {type(e).__name__}: {e}")
