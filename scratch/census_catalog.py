"""READ-ONLY: verify /v1/models completeness — provider prefix census + nvidia check."""
import json, sys, time
from collections import Counter
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
for a in range(5):
    try:
        s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45); break
    except Exception as e:
        print(f"login retry {a+1}: {type(e).__name__}"); time.sleep(10)

cat = None
for a in range(4):
    try:
        cat = s.get(f"{BASE}/v1/models", timeout=60).json(); break
    except Exception as e:
        print(f"catalog retry {a+1}: {type(e).__name__}"); time.sleep(8)
models = cat.get("data", [])
ids = [m.get("id") for m in models if isinstance(m, dict)]
print(f"total catalog ids: {len(ids)}")

# provider prefix census
pref = Counter()
for i in ids:
    if "/" in i:
        pref[i.split("/")[0]] += 1
    else:
        pref["<no-prefix>"] += 1
print("\n=== provider prefix census (top 40) ===")
for p, n in pref.most_common(40):
    print(f"  {n:5d}  {p}")

# is nvidia present at all?
nv = [i for i in ids if i.lower().startswith("nvidia")]
print(f"\nnvidia* in catalog: {len(nv)}")
for i in nv[:20]:
    print("   ", i)

# is the workhorse present under any spelling?
needle = "nemotron"
hits = [i for i in ids if needle in i.lower()]
print(f"\n'*{needle}*' in catalog: {len(hits)}")
for i in hits[:20]:
    print("   ", i)

# check a few combo models we flagged
for probe in ["nvidia/nemotron-3-super-120b-a12b","qoder/kimi-k3","lmarena/claude-sonnet-5","codex/gpt-5.6-sol","zai-web/glm-5.2","openrouter/openai/gpt-4o-mini","openrouter/z-ai/glm-4.5-air"]:
    print(f"  in-catalog {probe!r}: {probe in set(ids)}")

# are ANY openrouter/* models in the catalog?
orv = [i for i in ids if i.startswith("openrouter/")]
print(f"\nopenrouter/* in catalog: {len(orv)}")
for i in orv[:15]:
    print("   ", i)
