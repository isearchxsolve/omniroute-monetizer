"""sweep_all_video.py -- test EVERY video route in the inventory and prove which make a real MP4.

The only thing that counts as working here is a downloaded file whose bytes[4:8] == b"ftyp".
A 200, a job id, or a url is not a pass.

RULES HONOURED (operator's standing instructions):
  - ONE attempt per route. Never hammer. A 402/403/502-balance answer is information, not an
    invitation to retry.
  - The single exception is a duration-range complaint, which is OUR payload being wrong rather
    than the provider refusing us; that gets exactly one retry at a different duration.
  - Presigned media URLs are credential material. Only host + byte count are ever printed or
    saved -- never the query string.

Results are written incrementally so a long run can be reported on while still going.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

import requests

BASE = "http://localhost:20128"
GEN_URL = f"{BASE}/v1/videos/generations"
PROMPT = "a single red balloon drifting upward against a clear blue sky, slow steady shot"
GEN_TIMEOUT = 420          # real generations measured 35-140s; leave headroom
DOWNLOAD_TIMEOUT = 180
OUT_DIR = Path("state/video_proofs")
RESULTS = Path("state/video_proofs/sweep_all_results.json")

# Providers whose connection status already says the money is gone. Still tested -- a status field
# is a cached opinion, and the only authority is what the endpoint answers right now -- but tested
# LAST so the promising ones report first.
DEPRIORITISE = {"credits_exhausted", "expired", "error"}

# Text that means "this failed because of money", so we stop and never retry.
MONEY_RE = re.compile(
    r"credit|balance|insufficient|top ?up|payment required|quota|billing|subscribe|"
    r"upgrade your plan|exceeded|out of funds|no funds", re.I)
# Text that means our duration value was rejected -- worth exactly one different value.
DURATION_RE = re.compile(
    r"duration|within the specified range|value must be|invalid.*(?:length|seconds)", re.I)

_lock = threading.Lock()
_done: list[dict] = []


def load_prior() -> dict:
    """Carry forward results from earlier runs.

    BUG FIXED 2026-08-23: this file was rewritten from an empty list on every run, so each sweep
    silently erased the evidence from the last one -- the 14 chat-catalogue results disappeared the
    moment the registry sweep started, and video_capability_matrix.py then reported those routes as
    "not yet tested". Accumulated proof is the whole point of this file, so merge instead.
    """
    if not RESULTS.exists():
        return {}
    try:
        old = json.loads(RESULTS.read_text(encoding="utf-8"))
        return {r["model"]: r for r in old.get("results", []) if r.get("model")}
    except Exception as exc:
        print(f"  !! could not read prior results ({type(exc).__name__}); starting fresh")
        return {}


_prior: dict = {}


def safe_url(url: str) -> str:
    try:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}/...({len(url)} chars, query hidden)"
    except Exception:
        return f"<unparseable, {len(url)} chars>"


def extract_url(body: dict):
    data = body.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            for f in ("url", "video_url", "videoUrl", "b64_json"):
                if first.get(f):
                    return str(first[f]), f
    for f in ("url", "video_url", "output", "result"):
        if body.get(f):
            v = body[f]
            if isinstance(v, str):
                return v, f
            if isinstance(v, list) and v and isinstance(v[0], str):
                return v[0], f
    return None, None


def attempt(model: str, duration: int) -> tuple[int | None, dict | str, float]:
    payload = {"model": model, "prompt": PROMPT, "duration": duration,
               "aspect_ratio": "16:9", "n": 1}
    t0 = time.time()
    try:
        r = requests.post(GEN_URL, json=payload, timeout=GEN_TIMEOUT)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:140]}", round(time.time() - t0, 1)
    el = round(time.time() - t0, 1)
    try:
        return r.status_code, r.json(), el
    except Exception:
        return r.status_code, r.text[:300], el


def err_text(body) -> str:
    if isinstance(body, str):
        return body
    e = body.get("error") if isinstance(body, dict) else None
    if isinstance(e, dict):
        return str(e.get("message") or e)
    return str(e or body)[:400]


def test_route(provider: str, model: str, status: str, duration: int = 5) -> dict:
    res = {"provider": provider, "model": model, "conn_status": status, "duration": duration,
           "http": None, "elapsed_s": None, "bytes": None, "is_mp4": False,
           "verdict": "NOT_PROVEN", "reason": "", "detail": "", "saved": None}

    code, body, el = attempt(model, duration)
    res["http"], res["elapsed_s"] = code, el

    if code is None:
        res["reason"] = "TRANSPORT"
        res["detail"] = str(body)[:240]
        return _finish(res)

    if code != 200:
        msg = err_text(body)
        # Exactly one retry, and only when the complaint is about OUR duration value.
        if DURATION_RE.search(msg) and not MONEY_RE.search(msg):
            alt = 6 if duration != 6 else 10
            res["detail"] = f"duration {duration} rejected ({msg[:110]}); retried at {alt}. "
            code, body, el = attempt(model, alt)
            res.update(http=code, elapsed_s=el, duration=alt)
            if code != 200:
                msg = err_text(body)
                res["reason"] = "PAYWALL" if MONEY_RE.search(msg) else f"HTTP_{code}"
                res["detail"] += f"HTTP {code}: {msg[:220]}"
                return _finish(res)
        else:
            res["reason"] = "PAYWALL" if MONEY_RE.search(msg) else f"HTTP_{code}"
            res["detail"] = f"HTTP {code}: {msg[:240]}"
            return _finish(res)

    if not isinstance(body, dict):
        res["reason"] = "BAD_BODY"
        res["detail"] = f"HTTP 200 but body was not JSON: {str(body)[:180]}"
        return _finish(res)

    url, field = extract_url(body)
    if not url:
        res["reason"] = "NO_MEDIA_URL"
        res["detail"] = f"HTTP 200 but no media url; top-level fields: {sorted(body.keys())[:12]}"
        return _finish(res)

    res["detail"] = f"url in field '{field}': {safe_url(url)}. "
    try:
        dl = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    except Exception as exc:
        res["reason"] = "DOWNLOAD_FAILED"
        res["detail"] += f"download raised {type(exc).__name__}"
        return _finish(res)
    if dl.status_code != 200:
        res["reason"] = "DOWNLOAD_HTTP"
        res["detail"] += f"download returned HTTP {dl.status_code}"
        return _finish(res)

    blob = dl.content
    res["bytes"] = len(blob)
    res["is_mp4"] = len(blob) > 12 and blob[4:8] == b"ftyp"
    if not res["is_mp4"]:
        res["reason"] = "NOT_MP4"
        res["detail"] += (f"downloaded {len(blob)} bytes but bytes[4:8] != 'ftyp' "
                          f"(head hex {blob[:12].hex()}) -- NOT a video")
        return _finish(res)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"SWEEP_{provider}_{model.replace('/', '_').replace(':', '_')}.mp4"
    out.write_bytes(blob)
    res["verdict"] = "PROVEN"
    res["reason"] = "OK"
    res["saved"] = str(out)
    res["detail"] += f"real mp4, {len(blob)} bytes"
    return _finish(res)


def _finish(res: dict) -> dict:
    tag = "PROVEN " if res["verdict"] == "PROVEN" else f"{res['reason']:<14}"
    with _lock:
        _done.append(res)
        print(f"  [{len(_done):>2}] {tag} {res['provider']}/{res['model'][:52]:<52} "
              f"http={str(res['http']):<5} {res['elapsed_s']}s")
        if res["verdict"] == "PROVEN":
            print(f"       ^^^^ {res['bytes']} bytes -> {res['saved']}")
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        merged = dict(_prior)
        for r in _done:
            merged[r["model"]] = r        # this run's answer wins over any older one
        RESULTS.write_text(
            json.dumps({"prompt": PROMPT, "results": list(merged.values())}, indent=1),
            encoding="utf-8")
    return res


def main() -> int:
    global _prior
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated provider slugs")
    ap.add_argument("--routes", default="",
                    help="comma-separated FULL model ids to test, e.g. vertex/veo-3.0-generate-001."
                         " Use this to spend attempts on text-to-video only: an i2v/r2v/videoedit"
                         " route will always fail for want of an input image, and that failure"
                         " tells us nothing about whether the provider works.")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--from-registry", action="store_true",
                    help="take routes from the NATIVE video registry (the only real source of "
                         "truth for POST /v1/videos/generations) instead of the chat catalogue")
    ap.add_argument("--skip-exhausted", action="store_true",
                    help="don't test providers whose connection already says credits gone")
    args = ap.parse_args()

    _prior = load_prior()
    if _prior:
        print(f"  carrying forward {len(_prior)} results from earlier runs")

    want = {s.strip() for s in args.only.split(",") if s.strip()}
    pick = {s.strip() for s in args.routes.split(",") if s.strip()}
    routes = []

    if args.from_registry:
        # MEASURED 2026-08-23: the chat catalogue and the video registry are DIFFERENT THINGS.
        # Feeding chat ids to /v1/videos/generations returned 14 straight HTTP 400
        # "Invalid video model: <id>. Use format: provider/model" -- gemini/veo-3.1-*,
        # vertex/veo-3.1-* and all 8 orcarouter/kling/* are not video routes at all. The registry
        # extracted from the build is authoritative; always prefer it.
        reg = json.loads(Path("state/video_registry_native.json").read_text(encoding="utf-8"))
        keys = json.loads(Path("state/generated_keys.json").read_text(encoding="utf-8"))
        have = {k.lower() for k in keys}
        for slug, p in reg.items():
            if want and slug not in want:
                continue
            auth = p.get("authType", "?")
            cred = "no-auth" if auth == "none" else ("keyed" if slug.lower() in have else "no-key")
            for m in (p.get("models") or []):
                mid = m.get("id")
                if not mid or "__SEE_CHUNK" in mid:
                    continue
                routes.append((slug, f"{slug}/{mid}", cred, cred != "no-key"))
        # no-auth first, then the ones we hold a key for, then the rest
        rank = {"no-auth": 0, "keyed": 1, "no-key": 2}
        routes.sort(key=lambda r: (rank.get(r[2], 9), r[0], r[1]))
        if pick:
            routes = [r for r in routes if r[1] in pick]
            missing = pick - {r[1] for r in routes}
            if missing:
                print(f"  !! not in the registry, skipped: {sorted(missing)}")
    else:
        inv = json.loads(Path("state/video_route_inventory.json").read_text(encoding="utf-8"))
        for p in inv["providers"]:
            if want and p["provider"] not in want:
                continue
            st = p.get("test_status", "")
            if args.skip_exhausted and st in DEPRIORITISE:
                continue
            for m in p["video_models"]:
                routes.append((p["provider"], f"{p['provider']}/{m}", st, p.get("active", False)))
        routes.sort(key=lambda r: (not r[3], r[2] in DEPRIORITISE, r[0], r[1]))

    print("=" * 96)
    print(f"  VIDEO SWEEP -- {len(routes)} routes, {args.workers} at a time, one attempt each")
    print(f"  source: {'NATIVE VIDEO REGISTRY' if args.from_registry else 'chat catalogue'}")
    print("=" * 96)
    for p, m, st, ok in routes[:100]:
        print(f"    queued  {m:<52} ({st})")
    print()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(test_route, p, m, st) for p, m, st, _ in routes]
        for _ in as_completed(futs):
            pass

    proven = [r for r in _done if r["verdict"] == "PROVEN"]
    print()
    print("=" * 96)
    print(f"  RESULT: {len(proven)} PROVEN of {len(_done)} tested")
    print("=" * 96)
    for r in proven:
        print(f"    WORKS  {r['provider']}/{r['model']}  {r['bytes']} bytes  {r['elapsed_s']}s")
    if not proven:
        print("    none produced a real mp4")
    by = {}
    for r in _done:
        by.setdefault(r["reason"], []).append(f"{r['provider']}/{r['model']}")
    print("\n  failures by reason:")
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if k == "OK":
            continue
        print(f"    {k:<16} {len(v):>3}   e.g. {v[0]}")
    print(f"\n  full results: {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
