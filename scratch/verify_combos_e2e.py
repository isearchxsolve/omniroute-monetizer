"""End-to-end verification: live inference through core aliases + edited combos."""
import json, sys, time
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

TARGETS = [
    # 5 core aliases
    "frontier", "auto/best-coding", "auto/best-reasoning", "auto/best-chat", "kimi-coding",
    # 4 edited combos
    "auto/asian-flagships", "auto/pro-coding", "Frontier Max", "auto/free-chat",
]

body_tpl = {"messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 8, "stream": False}

results = []
for t in TARGETS:
    body = dict(body_tpl); body["model"] = t
    t0 = time.time()
    try:
        r = s.post(f"{BASE}/v1/chat/completions", json=body, timeout=90)
        dt = time.time() - t0
        if r.status_code == 200:
            j = r.json()
            content = ""
            try:
                content = j["choices"][0]["message"]["content"]
            except Exception:
                pass
            results.append((t, r.status_code, f"{dt:.1f}s", content.strip()[:40]))
        else:
            results.append((t, r.status_code, f"{dt:.1f}s", r.text[:80]))
    except Exception as e:
        results.append((t, "EXC", f"{time.time()-t0:.1f}s", f"{type(e).__name__}: {e}"[:80]))

print(f"{'target':28s} {'status':>7s} {'time':>7s}  reply")
print("-" * 80)
ok = 0
for t, st, dt, reply in results:
    mark = "OK " if st == 200 else "FAIL"
    if st == 200: ok += 1
    print(f"{t:28s} {str(st):>7s} {dt:>7s}  [{mark}] {reply}")
print(f"\n{ok}/{len(results)} targets returned 200 OK")
