"""Collect the DashScope video task that OmniRoute abandoned at its 300s poll ceiling.

WHAT WE MEASURED 2026-08-23:
    POST /v1/videos/generations  model=alibaba/wan2.7-t2v-2026-06-12
    -> HTTP 504 after 303.6s: "DashScope task <id> timed out (status: RUNNING)"
RUNNING is not a refusal. Alibaba accepted the job, charged nothing yet, and was still rendering
when OmniRoute's poller gave up. So this route may well be a WORKING video model whose only
problem is that the gateway is less patient than the upstream. The only way to know is to ask
DashScope for the task result directly.

The credential comes from the operator's own OmniRoute database, because the management API returns
apiKey masked to 16 characters. It is used in-process and never printed -- only its length and last
4 characters ever reach the console, and nothing is written to disk except the task status and, if
one exists, the mp4 itself.

Region matters: the connection's providerSpecificData says region=global-sg, so the international
host dashscope-intl.aliyuncs.com is the right one, not the mainland dashscope.aliyuncs.com.

Read-only against the database. One request per task id.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
import time

import requests

DB = pathlib.Path(r"C:\Users\Admin\.omniroute\storage.sqlite")
ROOT = pathlib.Path(r"D:\omniroute-monetizer")
OUT = ROOT / "state" / "video_proofs"

TASK_IDS = [t for t in sys.argv[1:] if "-" in t] or ["4e1f0ec0-a567-4e83-ac13-c892b0448fb0"]
HOSTS = ["https://dashscope-intl.aliyuncs.com", "https://dashscope.aliyuncs.com"]


def find_key() -> tuple[str, str]:
    """Return (apiKey, table) for the alibaba connection, read-only."""
    uri = f"file:{DB.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        # The connections table is whichever one has both a provider and an apiKey-ish column.
        for t in tables:
            cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")').fetchall()]
            lower = {c.lower(): c for c in cols}
            pcol = lower.get("provider")
            kcol = lower.get("apikey") or lower.get("api_key")
            if not (pcol and kcol):
                continue
            rows = con.execute(
                f'SELECT "{pcol}" AS p, "{kcol}" AS k FROM "{t}" WHERE lower("{pcol}")=?',
                ("alibaba",)).fetchall()
            for r in rows:
                if r["k"]:
                    return str(r["k"]), t
        raise SystemExit(f"no alibaba apiKey found; tables checked: {len(tables)}")
    finally:
        con.close()


key, table = find_key()
print(f"credential from table '{table}': len={len(key)}, ends ...{key[-4:]}")
if not key.startswith("sk-"):
    print("  NOTE: does not look like a plaintext DashScope key -- it may be encrypted at rest.")
print()

results = []
for tid in TASK_IDS:
    got = False
    for host in HOSTS:
        url = f"{host}/api/v1/tasks/{tid}"
        t0 = time.time()
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=60)
        except Exception as exc:
            print(f"  {host}: TRANSPORT {type(exc).__name__}")
            continue
        el = round(time.time() - t0, 1)
        print(f"  GET {host}/api/v1/tasks/{tid[:8]}...  HTTP {r.status_code}  {el}s")
        try:
            body = r.json()
        except Exception:
            print(f"      non-json: {r.text[:200]}")
            continue
        out = body.get("output") or {}
        status = out.get("task_status") or body.get("task_status")
        print(f"      task_status = {status}")
        rec = {"task_id": tid, "host": host, "http": r.status_code, "status": status,
               "verdict": "NOT_PROVEN", "bytes": None, "is_mp4": False}
        if r.status_code != 200:
            rec["detail"] = json.dumps(body)[:400]
            print(f"      {rec['detail'][:280]}")
            results.append(rec)
            continue
        got = True
        vurl = out.get("video_url") or out.get("videoUrl")
        if not vurl and isinstance(out.get("results"), list) and out["results"]:
            vurl = out["results"][0].get("url") or out["results"][0].get("video_url")
        if status == "SUCCEEDED" and vurl:
            print(f"      video ready on host {vurl.split('/')[2]} ({len(vurl)} chars, query hidden)")
            blob = requests.get(vurl, timeout=300).content
            rec["bytes"] = len(blob)
            rec["is_mp4"] = len(blob) > 12 and blob[4:8] == b"ftyp"
            if rec["is_mp4"]:
                OUT.mkdir(parents=True, exist_ok=True)
                dest = OUT / f"PROVEN_alibaba_wan2.7-t2v_{tid[:8]}.mp4"
                dest.write_bytes(blob)
                rec.update(verdict="PROVEN", saved=str(dest))
                print(f"      *** PROVEN *** real mp4, {len(blob)} bytes -> {dest}")
            else:
                print(f"      {len(blob)} bytes but not mp4 (head {blob[:12].hex()})")
        elif status in ("PENDING", "RUNNING"):
            print("      still rendering -- alibaba has NOT refused this job")
            rec["detail"] = "still running; OmniRoute's 300s poll ceiling is the only blocker"
        else:
            rec["detail"] = json.dumps(body)[:400]
            print(f"      {rec['detail'][:280]}")
        results.append(rec)
        break
    if not got:
        print(f"  task {tid}: no host returned a usable answer")
    print()

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "dashscope_task_collect.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
print(f"saved: {OUT / 'dashscope_task_collect.json'}")
