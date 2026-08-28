"""E2E verification of the :8190 consumer contract (worklog #1134 fixes).

Exercises the two paths the film-kit consumer (OiiOii/Codex) depends on:
  1. JSON-intent failover  — a "Return JSON only" chat must come back as STRICT JSON.
  2. Video job lifecycle   — immediate 202 receipt, idempotent job_key replay,
     lookup by job_id and by job_key, and cancellation semantics.

Run: python scratch_e2e_8190.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8190"
RESULTS = []


def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


print("=" * 70)
print("PATH 1 — JSON-intent failover (worklog #1134 fix 1)")
print("=" * 70)
st, resp = call("POST", "/v1/chat/completions", {
    "model": "session-pool/auto",
    "messages": [
        {"role": "system", "content": "You are a film-planning assistant."},
        {"role": "user", "content": (
            "Plan a 2-shot sequence for a neon alley scene. "
            "Return JSON only, no prose outside JSON. Shape: "
            '{"shots":[{"id":1,"prompt":"...","seconds":5}]}')},
    ],
})
content = ""
try:
    content = resp["choices"][0]["message"]["content"]
except Exception:
    pass
check("chat returns HTTP 200", st == 200, f"status={st}")
parsed = None
try:
    parsed = json.loads(content)
except Exception:
    pass
check("reply is STRICT JSON (json.loads succeeds)", parsed is not None,
      f"len={len(content)} head={content[:60]!r}")
check("reply is non-empty", len(content.strip()) > 0)
check("no markdown fence wrapping", not content.strip().startswith("```"),
      f"head={content[:20]!r}")
print(f"  provider={resp.get('provider')} session={resp.get('session')}")

print()
print("=" * 70)
print("PATH 2 — Video job lifecycle (worklog #1134 fixes 2-4)")
print("=" * 70)
job_key = f"e2e-{int(time.time())}"
print(f"  using job_key={job_key}")

# 2a. submit -> expect immediate 202 receipt
st, rec = call("POST", "/v1/chat/completions", {
    "model": "video/auto",
    "messages": [{"role": "user", "content": "A slow pan across a neon-lit alley at night."}],
    "video": {"job_key": job_key},
})
job_id = (rec.get("video") or {}).get("jobId") or rec.get("id")
check("submit returns 202 (immediate receipt)", st == 202, f"status={st}")
check("receipt carries jobId", bool(job_id), f"job_id={job_id}")
check("receipt carries statusUrl", bool((rec.get("video") or {}).get("statusUrl")))
check("receipt carries estimatedSeconds", (rec.get("video") or {}).get("estimatedSeconds") == 300)
print(f"  submit status={(rec.get('video') or {}).get('status')}")

# 2b. idempotent replay of the SAME job_key -> 200 + SAME job_id, no second render
st2, rec2 = call("POST", "/v1/chat/completions", {
    "model": "video/auto",
    "messages": [{"role": "user", "content": "A slow pan across a neon-lit alley at night."}],
    "video": {"job_key": job_key},
})
job_id2 = (rec2.get("video") or {}).get("jobId") or rec2.get("id")
check("replayed job_key returns 200 (not 202)", st2 == 200, f"status={st2}")
check("replay returns SAME job_id (idempotent)", job_id2 == job_id,
      f"{job_id} vs {job_id2}")

# 2c. lookup by job_id
st3, rec3 = call("GET", f"/v1/video/jobs/{job_id}")
check("GET by job_id returns 200", st3 == 200, f"status={st3}")
check("GET by job_id returns same record",
      ((rec3.get("video") or {}).get("jobId")) == job_id)

# 2d. lookup by job_key (reconciliation)
st4, rec4 = call("GET", f"/v1/video/jobs?job_key={job_key}")
check("GET by job_key returns 200", st4 == 200, f"status={st4}")
check("GET by job_key returns same record",
      ((rec4.get("video") or {}).get("jobId")) == job_id)

# 2e. poll a few times to observe status transitions
print("  polling status transitions (up to ~20s):")
seen = set()
for _ in range(10):
    _, r = call("GET", f"/v1/video/jobs/{job_id}")
    s = (r.get("video") or {}).get("status")
    seen.add(s)
    if s in ("succeeded", "failed", "cancelled"):
        break
    time.sleep(2)
print(f"    statuses observed: {sorted(x for x in seen if x)}")
check("job reached a terminal or running state",
      bool(seen & {"running", "succeeded", "failed"}), f"seen={sorted(x for x in seen if x)}")

# 2f. cancellation semantics
final_status = sorted(seen)[-1] if seen else ""
st5, rec5 = call("DELETE", f"/v1/video/jobs/{job_id}")
if final_status == "running":
    check("DELETE on running job returns 409 (honest no-cancel)", st5 == 409, f"status={st5}")
else:
    check("DELETE returns 200 (queued/terminal)", st5 in (200,), f"status={st5}")

# 2g. unknown job -> 404
st6, _ = call("GET", "/v1/video/jobs/does-not-exist")
check("GET unknown job returns 404", st6 == 404, f"status={st6}")

print()
print("=" * 70)
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print(f"RESULT: {passed}/{total} checks passed")
print("=" * 70)
if passed == total:
    print("E2E_PASS")
else:
    print("E2E_FAIL")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAILED: {name} {detail}")
