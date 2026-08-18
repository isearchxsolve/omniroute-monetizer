"""Perplexity E2E final verification — parse SSE stream for real content."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "automation"))
sys.stdout.reconfigure(encoding="utf-8")
from omniroute_api import OmniRouteAPI  # noqa: E402

api = OmniRouteAPI()
api.login()

for model in ["perplexity-web/pplx-sonar", "perplexity-web/pplx-auto"]:
    try:
        resp = api.session.post(
            f"{api.v1}/chat/completions",
            json={"model": model,
                  "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                  "max_tokens": 60},
            timeout=90,
        )
        print(f"{model}: HTTP {resp.status_code}")
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
                if content.strip():
                    print(f"  [LIVE-SSE] content: {content[:150]!r}")
                else:
                    print(f"  [EMPTY-SSE] no content in stream; raw head: {txt[:200]!r}")
            else:
                try:
                    j = resp.json()
                    c = j["choices"][0]["message"]["content"]
                    print(f"  [LIVE] content: {c[:150]!r}" if c.strip() else "  [EMPTY] no content")
                except Exception:
                    print(f"  body: {txt[:200]}")
        else:
            print(f"  body: {txt[:300]}")
    except Exception as e:
        print(f"{model}: EXC {type(e).__name__}: {e}")
    print()
