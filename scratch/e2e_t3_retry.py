"""t3-web E2E retry with backoff after 429 rate limit."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
sys.stdout.reconfigure(encoding="utf-8")
from omniroute_api import OmniRouteAPI  # noqa: E402

api = OmniRouteAPI()
api.login()

targets = ["t3-web/gpt-4o", "t3-web/gemini-2.5-flash", "t3-web/claude-haiku-4"]
for model in targets:
    for attempt in range(3):
        try:
            resp = api.session.post(
                f"{api.v1}/chat/completions",
                json={"model": model,
                      "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                      "max_tokens": 60},
                timeout=90,
            )
            print(f"{model} attempt {attempt+1}: HTTP {resp.status_code}")
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
                break
            elif resp.status_code == 429:
                print(f"  rate limited, waiting 10s...")
                time.sleep(10)
            else:
                print(f"  body: {txt[:300]}")
                break
        except Exception as e:
            print(f"{model}: EXC {type(e).__name__}: {e}")
            break
    print()
