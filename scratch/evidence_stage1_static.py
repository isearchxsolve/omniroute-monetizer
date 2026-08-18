"""Stage 1: Static evidence extraction for ALL providers.
Sources: registry TS files, executor inventory, ledger, live connections, live catalog.
Output: state/evidence/provider_evidence_static.json
No secrets ever written (T11): apiKey values redacted to presence booleans."""
import json, os, re, sys, datetime

sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

BASE = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute"
REG_DIR = os.path.join(BASE, "src", "shared", "constants", "providers")
EXEC_DIR = os.path.join(BASE, "open-sse", "executors")
OUT = "state/evidence/provider_evidence_static.json"

# ---------- 1. Parse registry TS files ----------
def parse_registry_file(path):
    """Extract provider entries from a TS registry file via brace-matching."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    entries = {}
    # Find top-level object literal entries: identifier: { ... }
    # We scan for lines matching `  slug: {` at 2-space indent (registry shape)
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r'^  "?([a-z0-9][a-z0-9-]*)"?:\s*\{\s*$', lines[i])
        if m:
            slug = m.group(1)
            # brace-match to find the entry end
            depth = 1
            j = i + 1
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                j += 1
            block = "\n".join(lines[i:j])
            entry = {"slug": slug}
            for field in ("id", "alias", "name", "website", "category"):
                fm = re.search(rf'\b{field}:\s*"([^"]*)"', block)
                if fm:
                    entry[field] = fm.group(1)
            for bfield in ("noAuth", "hasFree", "passthroughModels"):
                bm = re.search(rf'\b{bfield}:\s*(true|false)', block)
                if bm:
                    entry[bfield] = bm.group(1) == "true"
            sk = re.search(r'serviceKinds:\s*\[([^\]]*)\]', block)
            if sk:
                entry["serviceKinds"] = re.findall(r'"([^"]+)"', sk.group(1))
            # auth hint / free note / notice text (evidence of requirements)
            for tfield in ("authHint", "freeNote"):
                tm = re.search(rf'{tfield}:\s*\n?\s*"([^"]*)"', block)
                if tm:
                    entry[tfield] = tm.group(1)
            nm = re.search(r'notice:\s*\{[^}]*text:\s*"([^"]*)"', block, re.S)
            if nm:
                entry["noticeText"] = nm.group(1)
            entries[slug] = entry
            i = j
        else:
            i += 1
    return entries

registry = {}
registry_files = []
for root, _dirs, files in os.walk(REG_DIR):
    for fn in files:
        if fn.endswith(".ts"):
            registry_files.append(os.path.join(root, fn))
for rf in sorted(registry_files):
    parsed = parse_registry_file(rf)
    for slug, entry in parsed.items():
        entry["registryFile"] = os.path.relpath(rf, BASE).replace("\\", "/")
        registry[slug] = entry

print(f"registry providers parsed: {len(registry)} from {len(registry_files)} files")

# ---------- 2. Executor inventory ----------
executors = {}
for fn in sorted(os.listdir(EXEC_DIR)):
    if fn.endswith(".ts") and fn != "base.ts":
        name = fn[:-3]
        path = os.path.join(EXEC_DIR, fn)
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
        executors[name] = {
            "file": f"open-sse/executors/{fn}",
            "sizeBytes": os.path.getsize(path),
            "mentionsBootstrap": "bootstrap" in head.lower(),
            "mentionsCookie": "cookie" in head.lower(),
            "mentionsOAuth": "oauth" in head.lower() or "token" in head.lower(),
        }
print(f"executors found: {len(executors)}")

# ---------- 3. Ledger ----------
with open("state/all_296_providers_execution_ledger.json", encoding="utf-8") as f:
    ledger = json.load(f)["providers"]
ledger_by_slug = {p["slug"]: p for p in ledger}
print(f"ledger entries: {len(ledger_by_slug)}")

# ---------- 4. Live connections ----------
api = OmniRouteAPI()
api.login()
conns = api.get_connections()
conn_records = []
for c in conns:
    psd = c.get("providerSpecificData") or {}
    conn_records.append({
        "id": c.get("id"),
        "provider": c.get("provider"),
        "name": c.get("name"),
        "authType": c.get("authType"),
        "isActive": c.get("isActive"),
        "testStatus": c.get("testStatus"),
        "priority": c.get("priority"),
        "hasApiKey": bool(c.get("apiKey")),
        "psdKeys": sorted(psd.keys()),
    })
print(f"live connections: {len(conn_records)}")

# ---------- 5. Live catalog ----------
r = api.session.get(api.api.replace("/api", "") + "/api/synced-available-models", timeout=60)
catalog = r.json() if r.status_code == 200 else {}
catalog_slim = {p: [m.get("id") for m in models] for p, models in catalog.items()}
print(f"catalog providers: {len(catalog_slim)}")

# free-provider-rankings
r2 = api.session.get(api.api.replace("/api", "") + "/api/free-provider-rankings", timeout=60)
rankings = r2.json().get("rankings", []) if r2.status_code == 200 else []

# ---------- 6. Merge into evidence ----------
all_slugs = sorted(set(list(registry.keys()) + list(ledger_by_slug.keys()) + list(catalog_slim.keys())))
evidence = {}
for slug in all_slugs:
    reg = registry.get(slug, {})
    led = ledger_by_slug.get(slug, {})
    slug_conns = [c for c in conn_records if c["provider"] == slug]
    has_executor = slug in executors
    evidence[slug] = {
        "slug": slug,
        "registry": reg or None,
        "ledger_status": led.get("status"),
        "ledger_category": led.get("category"),
        "ledger_details": led.get("details"),
        "ledger_in_db_connections": led.get("in_db_connections"),
        "executor": executors.get(slug) if has_executor else None,
        "connections": slug_conns,
        "catalog_models": catalog_slim.get(slug),
        "in_free_rankings": any(rk.get("id") == slug for rk in rankings),
    }

os.makedirs("state/evidence", exist_ok=True)
out = {
    "generated_at": datetime.datetime.now().isoformat(),
    "omniroute_version": "3.8.49",
    "counts": {
        "registry": len(registry),
        "executors": len(executors),
        "ledger": len(ledger_by_slug),
        "connections": len(conn_records),
        "catalog_providers": len(catalog_slim),
        "merged_slugs": len(all_slugs),
    },
    "providers": evidence,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print(f"\nWROTE {OUT} ({os.path.getsize(OUT)} bytes)")

# quick coverage stats
no_reg = [s for s, e in evidence.items() if not e["registry"]]
no_exec = [s for s, e in evidence.items() if not e["executor"]]
no_conn = [s for s, e in evidence.items() if not e["connections"]]
no_cat = [s for s, e in evidence.items() if not e["catalog_models"]]
print(f"slugs missing registry entry: {len(no_reg)}")
print(f"slugs missing executor: {len(no_exec)}")
print(f"slugs missing connection: {len(no_conn)}")
print(f"slugs missing catalog models: {len(no_cat)}")
