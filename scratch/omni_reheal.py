"""Scoped, honest self-heal of stale-negative test_status (OmniRoute task 3 core).

The gateway benches is_active=1 connections whose last test_status is a stale negative and
never self-heals (OMNIROUTE_DISABLE_CREDENTIAL_HEALTH_CHECK=true). This re-tests ONLY the
benched CHAT connections via the supported per-connection endpoint (POST /api/providers/{id}/test).
It flips a route to 'active' ONLY if it actually answers now — honest, reversible, no restart,
off the request path. Never touches already-healthy routes; never touches video/media routes
(a 'test' there could spend real credits).

Writes a before/after backup to state/_reheal_backup_<ts>.json. Prints recovered vs still-benched.
No secrets are read or printed (metadata columns only).
"""
from __future__ import annotations
import json, os, sqlite3, sys, threading, time, pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI

DB = "file:C:/Users/Admin/.omniroute/storage.sqlite?mode=ro"
BENCHED = {"expired", "error", "credits_exhausted"}
# Skip anything that generates media — a per-connection 'test' could submit a paid job.
VIDEO_HINT = ("video", "veo", "flow", "vertex", "rtst", "topmedia", "digen", "capcut", "kling",
              "comfy", "segmind", "fal", "pollination", "replicate", "runpod", "kie", "runway",
              "luma", "pika", "hailuo", "vidu", "image", "img", "sdxl", "flux")


def is_video(provider: str) -> bool:
    p = (provider or "").lower()
    return any(h in p for h in VIDEO_HINT)


def read_active():
    con = sqlite3.connect(DB, uri=True, timeout=5)
    cols = [r[1] for r in con.execute("PRAGMA table_info(provider_connections)")]
    pick = [c for c in ["id", "name", "provider", "format", "test_status"] if c in cols]
    rows = list(con.execute(
        f"SELECT {','.join(pick)} FROM provider_connections WHERE is_active=1"))
    con.close()
    i = {c: n for n, c in enumerate(pick)}
    out = []
    for r in rows:
        out.append({
            "id": r[i["id"]],
            "provider": (r[i.get("provider", -1)] if "provider" in i else None) or (r[i.get("format", -1)] if "format" in i else None),
            "name": r[i["name"]] if "name" in i else None,
            "test_status": r[i["test_status"]] if "test_status" in i else None,
        })
    return out


_tl = threading.local()
def client() -> OmniRouteAPI:
    if not getattr(_tl, "api", None):
        a = OmniRouteAPI()
        assert a.login(), "management login failed"
        _tl.api = a
    return _tl.api


def retest(conn):
    t0 = time.time()
    res = client().test_connection(conn["id"])
    dt = int((time.time() - t0) * 1000)
    body = res.get("result") or {}
    valid = bool(body.get("valid")) if isinstance(body, dict) else False
    # some builds report success via status_code + status field instead of 'valid'
    if not valid and isinstance(body, dict):
        valid = str(body.get("status") or body.get("test_status") or "").lower() in ("active", "ok", "success", "working")
    err = body.get("error") or body.get("message") if isinstance(body, dict) else None
    return {**conn, "http": res.get("http_status"), "valid": valid, "ms": dt, "err": (str(err)[:90] if err else None)}


def main():
    active = read_active()
    targets = [c for c in active if str(c["test_status"]) in BENCHED and not is_video(c["provider"])]
    skipped_video = [c for c in active if str(c["test_status"]) in BENCHED and is_video(c["provider"])]
    ts = int(time.time())
    os.makedirs("state", exist_ok=True)
    with open(f"state/_reheal_backup_{ts}.json", "w") as f:
        json.dump({"ts": ts, "active_before": active}, f, indent=2, default=str)
    print(f"active={len(active)}  benched-chat targets={len(targets)}  skipped-video={len(skipped_video)}\n")

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(retest, c): c for c in targets}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                c = futs[fut]
                results.append({**c, "http": None, "valid": False, "ms": 0, "err": f"{type(e).__name__}: {str(e)[:80]}"})

    recovered = [r for r in results if r["valid"]]
    still = [r for r in results if not r["valid"]]
    recovered.sort(key=lambda x: x["provider"] or "")
    still.sort(key=lambda x: x["provider"] or "")
    print(f"=== RECOVERED (stale-negative -> now answers): {len(recovered)}/{len(targets)}")
    for r in recovered:
        print(f'   OK   {str(r["provider"]):16s} was={str(r["test_status"]):18s} {r["ms"]:6d}ms  {str(r["name"])[:26]}')
    print(f"\n=== STILL BENCHED (genuinely unavailable now): {len(still)}")
    for r in still:
        print(f'   --   {str(r["provider"]):16s} was={str(r["test_status"]):18s} http={r["http"]} err={r["err"]}')

    # ground truth: re-read DB distribution after
    after = read_active()
    from collections import Counter
    print("\n=== test_status distribution AFTER (active connections):")
    for st, n in Counter(str(c["test_status"]) for c in after).most_common():
        print(f"   {str(st):22s} {n}")
    routable = sum(1 for c in after if str(c["test_status"]) in ("active", "None"))
    print(f"\nROUTABLE POOL: {routable}/{len(after)} active connections now routable "
          f"(was 36 before). Backup: state/_reheal_backup_{ts}.json")


if __name__ == "__main__":
    main()
