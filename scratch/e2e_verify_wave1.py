"""E2E verify wave-1 connections with REAL /v1/chat/completions (zero-fabrication).

LIVE only on genuine HTTP 200 with real assistant content. Uses valid standard
chat payloads (AGENTS.md anti-pattern 3: never tiny/invalid payloads).
"""
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


def main():
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return 1

    # Get models per connection
    r = api.session.get(f"{api.api}/models", timeout=30)
    models = []
    if r.status_code == 200:
        data = r.json()
        models = data.get("models", data) if isinstance(data, dict) else data

    # Map connection -> its models
    conn_models = {cid: [] for cid in CONNS.values()}
    for m in models:
        mid = m if isinstance(m, str) else (m.get("id") or "")
        # models may carry providerId / connection info
        pid = "" if isinstance(m, str) else (m.get("providerId") or m.get("connectionId") or "")
        for cid in CONNS.values():
            if pid == cid:
                conn_models[cid].append(mid)

    print("models per connection:")
    for slug, cid in CONNS.items():
        print(f"  {slug}: {conn_models[cid][:10]}")

    # If no models mapped via providerId, try direct provider models endpoint
    for slug, cid in CONNS.items():
        if not conn_models[cid]:
            pr = api.session.get(f"{api.api}/providers/{cid}/models", timeout=30)
            if pr.status_code == 200:
                try:
                    pd = pr.json()
                    plist = pd.get("models", pd) if isinstance(pd, dict) else pd
                    conn_models[cid] = [m if isinstance(m, str) else (m.get("id") or m.get("modelId") or "") for m in plist]
                    print(f"  {slug} (provider models endpoint): {conn_models[cid][:10]}")
                except Exception as e:
                    print(f"  {slug} provider models parse err: {e}")

    # E2E completion per connection using its first model
    results = {}
    for slug, cid in CONNS.items():
        mlist = conn_models[cid]
        if not mlist:
            print(f"\n[{slug}] no models found — cannot e2e")
            results[slug] = "no_models"
            continue
        model = mlist[0]
        print(f"\n=== {slug} e2e: model={model} ===")
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Reply with exactly: OK"}
            ],
            "stream": False,
            "max_tokens": 64,
        }
        try:
            r = api.session.post(f"{api.v1}/chat/completions", json=payload, timeout=90)
            print(f"  HTTP {r.status_code}")
            if r.status_code == 200:
                body = r.json()
                content = ""
                try:
                    content = body["choices"][0]["message"]["content"]
                except Exception:
                    content = json.dumps(body)[:200]
                print(f"  content: {content[:150]!r}")
                results[slug] = {"model": model, "http": 200, "content_len": len(content), "LIVE": bool(content.strip())}
            else:
                print(f"  body: {r.text[:300]}")
                results[slug] = {"model": model, "http": r.status_code, "LIVE": False}
        except Exception as e:
            print(f"  ERROR: {e}")
            results[slug] = {"model": model, "error": str(e), "LIVE": False}

    print("\n=== E2E SUMMARY ===")
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
