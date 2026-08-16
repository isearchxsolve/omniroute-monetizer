"""Reorder multi-model combos MOST-POWERFUL -> LEAST-POWERFUL (user override of
the AGENTS.md Performance Invariant, confirmed via ask-questions).

RUNTIME MECHANICS (verified in dist/open-sse/mcp-server/server.js):
- orderTargetsForWeightedFallback sorts fallback targets by weight DESC.
- selectWeightedTarget picks the first target weight-biased.
=> Therefore cascade order == weight order. To get most-powerful-first we set
   weights in power order (highest weight = most powerful) AND reorder the array
   to match.

SAFETY:
- Backs up ALL combos to state/ BEFORE any write.
- DRY-RUN by default (pass --apply to PUT).
- Only touches combos with >1 model (single-model combos have nothing to order).
- Never restarts the service. Only PUT /api/combos.
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

# ---------------------------------------------------------------------------
# POWER RANKING (higher = more powerful). Judgment call by model-family class.
# Adjust here if you disagree with any placement.
# ---------------------------------------------------------------------------
POWER = {
    # frontier / top-tier reasoning & coding
    "ainative/claude-opus-4":                       100,
    "codex/gpt-5.6-sol":                             96,
    "ainative/claude-sonnet-4-5":                    92,
    "ainative/deepseek-r1":                          88,
    "alibaba/qwen3.7-max":                           84,
    "kimi-coding/kimi-coding-default":               80,
    # strong mid-tier
    "nvidia/nemotron-3-super-120b-a12b":             76,
    "alibaba/qwen3.7-plus":                          72,
    "zai-web/glm-5.2":                               68,
    "cerebras/zai-glm-4.7":                          64,
    "cerebras/gpt-oss-120b":                         60,
    # mid / assistant class
    "aion/aion-labs/aion-2.0":                       55,
    "amazon-q/amazon-q":                             50,
    # small / fast class
    "agnes/agnes-2.0-flash":                         44,
    "agnes/agnes-1.5-flash":                         40,
    "cerebras/gemma-4-31b":                          36,
    "cohere/c4ai-aya-expanse-32b":                   32,
    "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct":  20,
}
DEFAULT_POWER = 50  # unknown models -> middle


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


def main():
    s = login()
    rc = s.get(f"{BASE}/api/combos", timeout=45).json()
    combos = rc.get("combos", rc if isinstance(rc, list) else [])
    print(f"loaded {len(combos)} combos")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = rf"d:\omniroute-monetizer\state\combos_backup_powerorder_{ts}.json"
    with open(bak, "w", encoding="utf-8") as f:
        json.dump(combos, f, indent=2, default=str)
    print(f"BACKUP written: {bak}\n")

    changes = []
    for c in combos:
        name = c.get("name")
        cid = c.get("id")
        models = c.get("models", [])
        if len(models) < 2:
            print(f"skip {name!r}: {len(models)} model(s), nothing to order")
            continue

        # sort by power desc; stable for ties (keep original relative order)
        ranked = sorted(
            models,
            key=lambda m: POWER.get(m.get("model"), DEFAULT_POWER),
            reverse=True,
        )
        # assign strictly descending weights to lock the cascade order
        for i, m in enumerate(ranked):
            m["weight"] = 100 - (i * 5)

        before = [(m.get("model"), m.get("weight")) for m in models]
        after = [(m.get("model"), m.get("weight")) for m in ranked]
        if [b[0] for b in before] == [a[0] for a in after] and \
           [b[1] for b in before] == [a[1] for a in after]:
            print(f"skip {name!r}: already in power order")
            continue

        nc = dict(c)
        nc["models"] = ranked
        changes.append((cid, name, nc, before, after))

    print(f"\n=== PLANNED REORDER ({len(changes)} combos) ===")
    for cid, name, nc, before, after in changes:
        print(f"\n--- {name!r} (id={cid})")
        print("    BEFORE (model, weight):")
        for m, w in before:
            print(f"       w={w:<4} {m}  [power={POWER.get(m, DEFAULT_POWER)}]")
        print("    AFTER  (model, weight)  most->least powerful:")
        for m, w in after:
            print(f"       w={w:<4} {m}  [power={POWER.get(m, DEFAULT_POWER)}]")

    if not changes:
        print("\nNo changes needed.")
        return
    if not APPLY:
        print("\n[DRY-RUN] No writes. Re-run with --apply to execute.")
        return

    print("\n=== APPLYING ===")
    for cid, name, nc, before, after in changes:
        r = s.put(f"{BASE}/api/combos/{cid}", json=nc, timeout=60)
        print(f"  PUT {name!r}: {r.status_code} {'OK' if r.status_code == 200 else 'FAIL'}")
        if r.status_code != 200:
            print("     ", r.text[:400])

    # verify re-read
    time.sleep(2)
    rc2 = s.get(f"{BASE}/api/combos", timeout=45).json()
    combos2 = rc2.get("combos", rc2 if isinstance(rc2, list) else [])
    by_id = {c.get("id"): c for c in combos2}
    print("\n=== VERIFY (re-read weights) ===")
    for cid, name, nc, before, after in changes:
        cur = by_id.get(cid, {})
        seq = [(m.get("model"), m.get("weight")) for m in cur.get("models", [])]
        weights = [w for _, w in seq]
        mono = all(weights[i] >= weights[i+1] for i in range(len(weights)-1))
        print(f"  {name!r}: weights={weights} monotonic-desc={mono}")
        for m, w in seq:
            print(f"       w={w:<4} {m}")


if __name__ == "__main__":
    main()
