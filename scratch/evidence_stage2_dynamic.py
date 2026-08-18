"""Stage 2: Dynamic evidence for all providers with connections.
- test_connection for every connection (valid/invalid + diagnosis)
- bounded E2E probe for ACTIVE connections that have catalog models (first model only)
- app.log recent error extraction per provider
Output: state/evidence/provider_evidence_dynamic.json
T11: no secrets; only statuses/diagnosis text (truncated)."""
import json, os, sys, datetime, re, collections

sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

OUT = "state/evidence/provider_evidence_dynamic.json"
APPLOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

api = OmniRouteAPI()
api.login()
conns = api.get_connections()

# Load static evidence for catalog models
with open("state/evidence/provider_evidence_static.json", encoding="utf-8") as f:
    static = json.load(f)
prov_static = static["providers"]

results = {"connection_tests": [], "e2e_probes": [], "log_errors": {}}

# ---------- 1. test_connection for every connection ----------
print(f"=== testing {len(conns)} connections ===")
for c in conns:
    cid = c.get("id")
    slug = c.get("provider")
    try:
        tc = api.test_connection(cid)
        res = tc.get("result") or {}
        results["connection_tests"].append({
            "connection_id": cid,
            "provider": slug,
            "isActive": c.get("isActive"),
            "authType": c.get("authType"),
            "http_status": tc.get("http_status"),
            "valid": res.get("valid"),
            "error": (res.get("error") or "")[:200],
            "diagnosis_type": (res.get("diagnosis") or {}).get("type"),
            "diagnosis_msg": ((res.get("diagnosis") or {}).get("message") or "")[:200],
        })
        print(f"  {slug:26s} valid={res.get('valid')} err={(res.get('error') or '')[:60]}")
    except Exception as e:
        results["connection_tests"].append({
            "connection_id": cid, "provider": slug, "isActive": c.get("isActive"),
            "authType": c.get("authType"), "exception": str(e)[:200],
        })
        print(f"  {slug:26s} EXC {str(e)[:60]}")

# ---------- 2. bounded E2E for active conns with catalog models ----------
print("\n=== bounded E2E probes (active conns w/ catalog models) ===")
probed = set()
for c in conns:
    slug = c.get("provider")
    if not c.get("isActive"):
        continue
    if slug in probed:
        continue
    models = (prov_static.get(slug) or {}).get("catalog_models") or []
    if not models:
        continue
    model = models[0]
    fq = f"{slug}/{model}"
    probed.add(slug)
    try:
        r = api.session.post(api.v1 + "/chat/completions",
            json={"model": fq,
                  "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                  "max_tokens": 60, "stream": False}, timeout=90)
        body = r.text
        content = ""
        try:
            j = r.json()
            ch = (j.get("choices") or [{}])[0]
            content = ((ch.get("message") or {}).get("content") or "")[:80]
        except Exception:
            pass
        results["e2e_probes"].append({
            "provider": slug, "model": fq, "http_status": r.status_code,
            "has_content": bool(content.strip()), "content_preview": content,
            "body_preview": body[:200],
        })
        print(f"  {fq:45s} {r.status_code} content={bool(content.strip())}")
    except Exception as e:
        results["e2e_probes"].append({"provider": slug, "model": fq, "exception": str(e)[:200]})
        print(f"  {fq:45s} EXC {str(e)[:60]}")

# ---------- 3. app.log recent errors per provider ----------
print("\n=== extracting app.log errors per provider ===")
err_pat = re.compile(r'\[(ERROR|WARN)\]|"level":(40|50)|❌|error')
prov_errs = collections.defaultdict(list)
try:
    with open(APPLOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            low = line.lower()
            if "error" not in low and '"level":40' not in line and '"level":50' not in line and "❌" not in line:
                continue
            # attribute to a provider slug if present
            for slug in prov_static:
                if slug in line:
                    if len(prov_errs[slug]) < 5:
                        prov_errs[slug].append(line.strip()[:250])
                    break
except Exception as e:
    print("log read error:", e)
results["log_errors"] = {k: v for k, v in prov_errs.items() if v}
print(f"providers with log errors: {len(results['log_errors'])}")

os.makedirs("state/evidence", exist_ok=True)
out = {"generated_at": datetime.datetime.now().isoformat(), **results}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print(f"\nWROTE {OUT} ({os.path.getsize(OUT)} bytes)")
print(f"connection_tests={len(results['connection_tests'])} e2e_probes={len(results['e2e_probes'])} log_err_providers={len(results['log_errors'])}")
