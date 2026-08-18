"""E2E wave-1 with provider-prefixed models (skip slow /v1/models)."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

CONNS = {
    "perplexity-web": "3b45f2bf-f1aa-4162-a305-ace36bddd4b7",
    "t3-web": "ef5082c2-e57e-4a6d-8e99-0e0cad698fbd",
}

pw = resolve_password()
api = OmniRouteAPI(password=pw)
api.login()

results = {}
for slug, cid in CONNS.items():
    # Get models for this connection
    pr = api.session.get(f"{api.api}/providers/{cid}/models", timeout=30)
    mlist = []
    if pr.status_code == 200:
        pd = pr.json()
        plist = pd.get("models", pd) if isinstance(pd, dict) else pd
        mlist = [m if isinstance(m, str) else (m.get("id") or m.get("modelId") or "") for m in plist]
    print(f"\n=== {slug}: {len(mlist)} models: {mlist[:8]} ===")
    if not mlist:
        results[slug] = "no_models"
        continue

    # Try first 2 models with provider prefix
    for model_raw in mlist[:2]:
        model = f"{slug}/{model_raw}"
        print(f"\n  trying model={model}")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "stream": False,
            "max_tokens": 64,
        }
        try:
            r = api.session.post(f"{api.v1}/chat/completions", json=payload, timeout=90)
            print(f"    HTTP {r.status_code}")
            if r.status_code == 200:
                body = r.json()
                content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"    content: {content[:120]!r}")
                results[slug] = {"model": model, "http": 200, "LIVE": bool(content.strip())}
                break
            else:
                print(f"    body: {r.text[:250]}")
                results[slug] = {"model": model, "http": r.status_code, "LIVE": False}
        except Exception as e:
            print(f"    ERROR: {e}")
            results[slug] = {"model": model, "error": str(e)[:100], "LIVE": False}

print("\n=== E2E SUMMARY ===")
print(json.dumps(results, indent=2, default=str))
