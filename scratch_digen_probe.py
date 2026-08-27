# -*- coding: utf-8 -*-
"""Probe digen.ai token liveness with a READ-ONLY poll (no video generation).

The DigenSessionClient extracts Digen-Token headers from the recorded_job exchanges.
A GET to the queue/list endpoint authenticates the token WITHOUT spending generation
credits. This tells us whether the captured session is still alive before we commit
to a full submit->poll->video run.
"""
import json, pathlib, requests

raw = json.loads(pathlib.Path("state/secrets/session_digen_ai.json").read_text(encoding="utf-8"))
exchanges = raw["recorded_job"].get("exchanges", [])
print("exchange count:", len(exchanges))

_DROP_HDR = {"content-length", "accept-encoding", "cookie"}
headers = {}
for ex in exchanges:
    h = ex.get("request_headers", {})
    if "Digen-Token" in h:
        for k, v in h.items():
            if not k.startswith(":") and k.lower() not in _DROP_HDR:
                headers[k] = v
        break

if not headers:
    print("NO Digen-Token found in exchanges")
    raise SystemExit(1)

print("header names:", sorted(headers.keys()))
print("Digen-Token present:", "Digen-Token" in headers, "(len %d)" % len(headers.get("Digen-Token", "")))
headers["accept-encoding"] = "gzip, deflate"

# Show the URLs captured so we know the real endpoints
print("\ncaptured exchange URLs:")
for ex in exchanges:
    print("  ", ex.get("method"), ex.get("url"))

# READ-ONLY poll — authenticates token, spends nothing
poll_url = "https://api.digen.ai/v1/queue/list?page=0&pageSize=10&status=3"
try:
    r = requests.get(poll_url, headers=headers, timeout=20)
    print("\nPOLL status:", r.status_code)
    body = r.text[:400]
    print("POLL body:", body)
    if r.status_code == 200:
        try:
            j = r.json()
            print("errCode:", j.get("errCode"), "errMsg:", j.get("errMsg"))
            jobs = (j.get("data") or {}).get("list") or []
            print("jobs in queue:", len(jobs))
            if j.get("errCode") == 0:
                print("VERDICT: TOKEN_ALIVE (read-only poll 200, errCode 0)")
            else:
                print("VERDICT: TOKEN_REJECTED_BY_API (errCode != 0)")
        except Exception as e:
            print("non-JSON body:", e)
    elif r.status_code in (401, 403):
        print("VERDICT: TOKEN_EXPIRED (HTTP %d)" % r.status_code)
    else:
        print("VERDICT: UNEXPECTED_HTTP_%d" % r.status_code)
except requests.RequestException as e:
    print("NETWORK error:", e)
