"""Fix dead combo models: swap inactive-provider models for verified-live ones.

SAFETY:
- Backs up ALL combos to state/combos_backup_<ts>.json BEFORE any write.
- DRY-RUN by default (pass --apply to actually PUT).
- A model is 'dead' only if its provider connection has NO active connection
  (authoritative provider-status signal, NOT the unreliable /v1/models catalog).
- Replacement = verified-live model from an ACTIVE provider. If the replacement
  already exists in the same combo, the dead entry is REMOVED instead (no dupes).
- Never touches combos whose models are all active. Never restarts the service.
"""
import json
import sys
import time
from datetime import datetime

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

APPLY = "--apply" in sys.argv

# dead model -> verified-live replacement (all replacements from ACTIVE providers)
REPLACEMENTS = {
    "qoder/kimi-k3":                 "kimi-coding/kimi-coding-default",
    "qoder/qwen3.8-max-preview":     "alibaba/qwen3.7-max",
    "qoder/qwen3.7-max":             "alibaba/qwen3.7-plus",
    "qoder/glm-5.2":                 "zai-web/glm-5.2",
    "lmarena/claude-sonnet-5":       "ainative/claude-sonnet-4-5",
    "lmarena/deepseek-v4-pro-thinking": "ainative/deepseek-r1",
    "lmarena/gpt-5.2-high":          "codex/gpt-5.6-sol",
    "grok-cli/grok-4.5":             "cerebras/gpt-oss-120b",
}


def login():
    s = requests.Session()
    for a in range(5):
        try:
            r = s.post(f"{BASE}/api/auth/login",
                       json={"password": resolve_password()}, timeout=45)
            if r.status_code == 200:
                return s
        except Exception as e:
            print(f"  login retry {a+1}: {type(e).__name__}")
            time.sleep(10)
    raise SystemExit("FATAL: could not login")


def active_providers(s):
    """provider name -> True if it has at least one isActive connection."""
    rp = s.get(f"{BASE}/api/providers", timeout=45).json()
    conns = rp.get("connections", [])
    act = {}
    for c in conns:
        p = c.get("provider")
        if c.get("isActive"):
            act[p] = True
        else:
            act.setdefault(p, False)
    return act


def main():
    s = login()
    act = active_providers(s)

    rc = s.get(f"{BASE}/api/combos", timeout=45).json()
    combos = rc.get("combos", rc if isinstance(rc, list) else [])
    print(f"loaded {len(combos)} combos")

    # ---- BACKUP (always, before any write) ----
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = rf"d:\omniroute-monetizer\state\combos_backup_{ts}.json"
    with open(bak, "w", encoding="utf-8") as f:
        json.dump(combos, f, indent=2, default=str)
    print(f"BACKUP written: {bak}")

    changes = []  # (combo_id, combo_name, new_combo_obj, list_of_edits)

    for c in combos:
        name = c.get("name")
        cid = c.get("id")
        models = c.get("models", [])
        if not models:
            continue

        present = {m.get("model") for m in models if isinstance(m, dict)}
        new_models = []
        edits = []
        for e in models:
            if not isinstance(e, dict):
                new_models.append(e)
                continue
            model = e.get("model")
            pid = e.get("providerId") or e.get("provider") or ""
            prov_active = act.get(pid, False)

            if prov_active:
                new_models.append(e)  # keep as-is
                continue

            # dead provider -> try replacement
            repl = REPLACEMENTS.get(model)
            if repl and repl not in present:
                ne = dict(e)
                ne["model"] = repl
                ne["providerId"] = repl.split("/")[0]
                new_models.append(ne)
                present.add(repl)
                edits.append(f"SWAP   {model!r} -> {repl!r}")
            else:
                reason = "no mapping" if not repl else "replacement already present"
                edits.append(f"REMOVE {model!r} ({reason}; provider {pid!r} inactive)")

        if edits:
            nc = dict(c)
            nc["models"] = new_models
            changes.append((cid, name, nc, edits))

    # ---- report ----
    print(f"\n=== PLANNED CHANGES ({len(changes)} combos) ===")
    for cid, name, nc, edits in changes:
        print(f"\n--- {name!r} (id={cid})")
        for ed in edits:
            print(f"    {ed}")
        print(f"    resulting models ({len(nc['models'])}):")
        for m in nc["models"]:
            print(f"       [w={m.get('weight')}] {m.get('model')!r} prov={m.get('providerId')!r}")

    if not changes:
        print("\nNo changes needed.")
        return

    if not APPLY:
        print("\n[DRY-RUN] No writes performed. Re-run with --apply to execute.")
        return

    # ---- apply ----
    print("\n=== APPLYING ===")
    for cid, name, nc, edits in changes:
        r = s.put(f"{BASE}/api/combos/{cid}", json=nc, timeout=60)
        ok = r.status_code == 200
        print(f"  PUT {name!r}: {r.status_code} {'OK' if ok else 'FAIL'}")
        if not ok:
            print("     ", r.text[:400])

    # ---- verify by re-reading ----
    print("\n=== VERIFY (re-read) ===")
    time.sleep(2)
    rc2 = s.get(f"{BASE}/api/combos", timeout=45).json()
    combos2 = rc2.get("combos", rc2 if isinstance(rc2, list) else [])
    by_id = {c.get("id"): c for c in combos2}
    still_dead = 0
    for cid, name, nc, edits in changes:
        cur = by_id.get(cid, {})
        for m in cur.get("models", []):
            pid = m.get("providerId") or ""
            if not act.get(pid, False):
                still_dead += 1
                print(f"  STILL DEAD in {name!r}: {m.get('model')!r} prov={pid!r}")
    print(f"  remaining dead models in edited combos: {still_dead}")


if __name__ == "__main__":
    main()
