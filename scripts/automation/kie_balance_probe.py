"""How many credits does the kie.ai account actually have RIGHT NOW?

WHY THIS EXISTS:
The robot Chrome profile re-authenticated to kie.ai by itself via Google one-tap (the operator saw
"Successfully signed in!" and the API Keys page confirms it: account Kunal Das /
isearch.xsolve@gmail.com, a single key named "Default" created 2026-07-06). That is the SAME account
whose 16 video routes all answered "credits insufficient" on 2026-08-23, so being signed in does not
by itself unlock anything -- the balance does. The billing page animates continuously and starves
Playwright's screenshot/stability wait, so ask kie.ai's own API instead. It is the authority anyway.

kie.ai exposes the balance at GET /api/v1/chat/credit (documented alongside their generation
endpoints). Several older deployments answered on /api/v1/common/credit, so both are tried and every
answer is reported verbatim -- an unexpected 404 is data, not a failure.

SECRET HANDLING: the key is read from the gitignored harvest file, used in-process, and only its
length and last 4 characters ever reach the console or the saved artifact.
"""
from __future__ import annotations

import json
import pathlib
import time

import requests

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
KEYS = ROOT / "state" / "generated_keys.json"
OUT = ROOT / "state" / "kie_balance.json"

ENDPOINTS = [
    "https://api.kie.ai/api/v1/chat/credit",
    "https://api.kie.ai/api/v1/common/credit",
    "https://kie.ai/api/v1/chat/credit",
]


def load_key() -> str:
    d = json.loads(KEYS.read_text(encoding="utf-8"))
    v = d.get("kie")
    if isinstance(v, dict):
        for f in ("key", "api_key", "apiKey", "token", "value"):
            if v.get(f):
                return str(v[f])
        raise SystemExit(f"kie entry has no key field; fields={sorted(v)}")
    if isinstance(v, str) and v:
        return v
    raise SystemExit("no kie key in state/generated_keys.json")


key = load_key()
print(f"kie key: len={len(key)}, ends ...{key[-4:]}")
print()

rows = []
for url in ENDPOINTS:
    t0 = time.time()
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {key}",
                                       "Accept": "application/json"}, timeout=45)
    except Exception as exc:
        print(f"  {url}\n      TRANSPORT {type(exc).__name__}: {str(exc)[:120]}")
        rows.append({"url": url, "http": None, "error": type(exc).__name__})
        continue
    el = round(time.time() - t0, 1)
    try:
        body = r.json()
    except Exception:
        body = r.text[:300]
    print(f"  {url}")
    print(f"      HTTP {r.status_code}  {el}s   {json.dumps(body)[:300]}")
    rows.append({"url": url, "http": r.status_code, "elapsed_s": el, "body": body})
    if r.status_code == 200:
        break

print()
best = next((x for x in rows if x.get("http") == 200), None)
if not best:
    print("VERDICT: could not read a balance from any endpoint -- see the answers above.")
else:
    b = best["body"]
    # kie wraps payloads as {"code":200,"msg":"success","data":<number or object>}
    val = b.get("data") if isinstance(b, dict) else b
    if isinstance(val, dict):
        val = val.get("credit", val.get("credits", val.get("balance", val)))
    print(f"VERDICT: kie.ai reports credits = {val}")
    try:
        if float(val) > 0:
            print("  -> there IS spendable balance; a video attempt is worth making.")
        else:
            print("  -> ZERO balance. This is the exhausted account, exactly as warned. Signing in")
            print("     changed the session, not the money. A genuinely different email is needed,")
            print("     and no attempt should be spent on this one.")
    except Exception:
        print("  -> balance is not a plain number; printed verbatim above.")

OUT.write_text(json.dumps({"key_len": len(key), "key_tail": key[-4:], "probes": rows}, indent=1),
               encoding="utf-8")
print(f"\nsaved: {OUT}")
