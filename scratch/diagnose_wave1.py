"""Diagnose wave-1 e2e failures: check model routing + perplexity subscription."""
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

# 1. Check /v1/models to see how models are namespaced
r = api.session.get(f"{api.v1}/models", timeout=30)
print(f"/v1/models HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    models = data.get("data", data.get("models", []))
    print(f"total models: {len(models)}")
    # Find t3-web and perplexity models
    for m in models:
        mid = m.get("id", "") if isinstance(m, dict) else m
        if any(k in mid.lower() for k in ["pplx", "t3", "claude-opus", "claude-sonnet"]):
            owned = m.get("owned_by", "") if isinstance(m, dict) else ""
            print(f"  {mid} (owned_by={owned})")

# 2. Check connection details
for slug, cid in CONNS.items():
    r = api.session.get(f"{api.api}/providers/{cid}", timeout=20)
    print(f"\n{slug} connection detail: HTTP {r.status_code}")
    if r.status_code == 200:
        c = r.json()
        conn = c.get("connection", c)
        print(f"  provider={conn.get('provider')} authType={conn.get('authType')} "
              f"active={conn.get('isActive')} testStatus={conn.get('testStatus')}")
        psd = conn.get("providerSpecificData", {})
        if psd:
            print(f"  providerSpecificData keys: {list(psd.keys())}")

# 3. Try e2e with provider-prefixed model
print("\n=== e2e with provider-prefixed models ===")
for slug, cid in CONNS.items():
    # Get models for this connection
    pr = api.session.get(f"{api.api}/providers/{cid}/models", timeout=30)
    mlist = []
    if pr.status_code == 200:
        pd = pr.json()
        plist = pd.get("models", pd) if isinstance(pd, dict) else pd
        mlist = [m if isinstance(m, str) else (m.get("id") or m.get("modelId") or "") for m in plist]
    if not mlist:
        print(f"  {slug}: no models")
        continue
    # Try with provider prefix
    model = f"{slug}/{mlist[0]}"
    print(f"\n  {slug}: trying model={model}")
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
            print(f"    content: {content[:100]!r}")
        else:
            print(f"    body: {r.text[:300]}")
    except Exception as e:
        print(f"    ERROR: {e}")
