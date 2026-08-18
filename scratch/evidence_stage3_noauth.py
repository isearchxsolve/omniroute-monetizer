"""Stage 3: noAuth / connectionless provider probes.
These providers route without a connection row. Probe each LLM-kind noAuth provider
with a bounded E2E to capture upstream behavior evidence.
Output: state/evidence/provider_evidence_noauth.json"""
import json, os, sys, datetime

sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

OUT = "state/evidence/provider_evidence_noauth.json"

with open("state/evidence/provider_evidence_static.json", encoding="utf-8") as f:
    static = json.load(f)
prov = static["providers"]

# noAuth providers with llm service kind (or no serviceKinds recorded but noAuth)
noauth_llm = []
for slug, e in prov.items():
    reg = e.get("registry") or {}
    if reg.get("noAuth"):
        kinds = reg.get("serviceKinds") or ["llm"]
        noauth_llm.append((slug, kinds, reg.get("alias"), reg.get("name")))

print(f"noAuth providers in registry: {len(noauth_llm)}")
for s, k, a, n in noauth_llm:
    print(f"  {s:24s} kinds={k} name={n}")

api = OmniRouteAPI()
api.login()

results = []
for slug, kinds, alias, name in noauth_llm:
    if "llm" not in kinds:
        results.append({"provider": slug, "skipped": True, "reason": f"serviceKinds={kinds} (non-LLM)"})
        print(f"  SKIP {slug} (kinds={kinds})")
        continue
    # pick a model: catalog first, else try common defaults
    models = (prov.get(slug) or {}).get("catalog_models") or []
    candidates = models[:2] if models else ["auto", "default"]
    for m in candidates:
        fq = f"{slug}/{m}"
        try:
            r = api.session.post(api.v1 + "/chat/completions",
                json={"model": fq,
                      "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                      "max_tokens": 60, "stream": False}, timeout=90)
            content = ""
            try:
                j = r.json()
                ch = (j.get("choices") or [{}])[0]
                content = ((ch.get("message") or {}).get("content") or "")[:80]
            except Exception:
                pass
            results.append({
                "provider": slug, "model": fq, "http_status": r.status_code,
                "has_content": bool(content.strip()), "content_preview": content,
                "body_preview": r.text[:250],
            })
            print(f"  {fq:40s} {r.status_code} content={bool(content.strip())} {r.text[:80]}")
            if r.status_code == 200 and content.strip():
                break  # found a working model, stop candidates
        except Exception as e:
            results.append({"provider": slug, "model": fq, "exception": str(e)[:200]})
            print(f"  {fq:40s} EXC {str(e)[:60]}")

os.makedirs("state/evidence", exist_ok=True)
out = {"generated_at": datetime.datetime.now().isoformat(), "probes": results}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print(f"\nWROTE {OUT} ({os.path.getsize(OUT)} bytes), {len(results)} probes")
