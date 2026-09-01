#!/usr/bin/env python3
"""
Probe OmniRoute's native video endpoint (``POST /v1/videos/generations``) and report,
per candidate model, whether it actually returns a usable video payload.

This is the ground-truth gate before the OiiOii Animator agent is pointed at OmniRoute.
It exists because the previous diagnosis ("video is 401/400, wire an API key") was
aimed at endpoints and model ids that do not exist in OmniRoute's video registry. So
this tool never invents a model string: every candidate comes from the compiled
``VIDEO_PROVIDERS`` registry via :mod:`video_registry`, cross-referenced against the
live ``/api/providers`` connection list.

Ranking rationale (cheapest-thing-that-can-work first):
  1. zero-auth providers        — need no credential at all
  2. active connection + key    — credential already present and healthy
  3. inactive connection + key  — credential present, connection disabled
  4. no connection              — would need provisioning

Never writes to OmniRoute. Never logs a secret.

Usage:
    python scripts/automation/video_provider_probe.py                 # probe ranked shortlist
    python scripts/automation/video_provider_probe.py --plan-only     # show plan, no calls
    python scripts/automation/video_provider_probe.py --all           # probe every model
    python scripts/automation/video_provider_probe.py --model kie/veo/veo-3-1
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from omniroute_api import BASE_URL, STATE_DIR, OmniRouteAPI, redact, redact_url  # noqa: E402
from video_registry import (  # noqa: E402
    DEFAULT_OMNIROUTE_DIST,
    annotate_supported,
    flatten_models,
    load_registry,
)

# Login is bcrypt-bound and measured at ~9.5s on this host; the shared client's 15s
# ceiling is too tight and flakes. Probing must never fail for that reason.
LOGIN_TIMEOUT = 120

# A video request is a real generation job, and dashscope-class providers are async
# (submit + poll a task url) so the router can hold the connection for minutes.
# Overridable per-run: reachability probes want it short, real renders want it long.
GEN_TIMEOUT = 150
REPORT_PATH = STATE_DIR / "video_provider_probe.json"
PLAN_PATH = STATE_DIR / "video_probe_plan.json"
ADMISSION_PATH = STATE_DIR / "omniroute_verified_video_routes.json"
REPORT_SCHEMA = 2
OMNI_BASE = BASE_URL.replace("localhost", "127.0.0.1")
DURATION_FALLBACKS = (4, 6, 8)

# Models that cannot be driven by a text prompt alone. The router rejects these with
# "Image input is required" / "Video input is required", which is a correct response to
# a malformed request, not a provider fault — so they are worthless as health probes.
# The Animator is text-to-video, so these are out of scope for the pipeline anyway.
NON_T2V_MARKERS = ("i2v", "r2v", "image-to-video", "videoedit", "video-edit", "-ref", "ti2v")

PROMPT = (
    "A slow cinematic dolly-in on a lone astronaut standing at the edge of a vast "
    "red canyon at golden hour, dust drifting through low sunlight, shot on 35mm."
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _tier(provider: str, auth_type: str, conns_by_provider: Dict[str, List[dict]]) -> tuple[int, str]:
    """Return (rank, human reason). Lower rank = try earlier."""
    if auth_type.lower() == "none":
        return 0, "zero-auth (no credential required)"
    rows = conns_by_provider.get(provider, [])
    if not rows:
        return 3, "no connection configured"
    active_keyed = [c for c in rows if c.get("isActive") and c.get("apiKey")]
    if active_keyed:
        return 1, f"active connection with credential ({len(active_keyed)})"
    active = [c for c in rows if c.get("isActive")]
    if active:
        return 1, f"active connection, no api key field ({len(active)})"
    keyed = [c for c in rows if c.get("apiKey")]
    if keyed:
        return 2, f"inactive connection with credential ({len(keyed)})"
    return 2, "inactive connection, no credential"


def is_text_to_video(qualified: str) -> bool:
    low = qualified.lower()
    return not any(mark in low for mark in NON_T2V_MARKERS)


def build_plan(registry: Dict[str, Any], connections: List[dict], shortlist: bool) -> List[Dict[str, Any]]:
    conns_by_provider: Dict[str, List[dict]] = {}
    for c in connections:
        conns_by_provider.setdefault(str(c.get("provider") or ""), []).append(c)

    models = flatten_models(registry)
    for m in models:
        rank, reason = _tier(m["provider"], m["authType"], conns_by_provider)
        m["rank"] = rank
        m["reason"] = reason
        definition = registry.get(m["provider"]) or {}
        m["handlerImplemented"] = bool(definition.get("handlerImplemented", True))
        m["textToVideo"] = is_text_to_video(m["qualified"])

    models.sort(key=lambda m: (m["rank"], m["provider"], m["model"]))
    if not shortlist:
        return models

    # Shortlist: only providers whose format has a handler (others 400 unconditionally,
    # so probing them measures nothing) and only text-to-video models. Rank 0-2 means a
    # credential is already present or unnecessary. Two models per provider keeps the
    # sweep broad across providers rather than deep in one catalogue.
    out: List[Dict[str, Any]] = []
    per_provider: Dict[str, int] = {}
    for m in models:
        if m["rank"] > 2 or not m["handlerImplemented"] or not m["textToVideo"]:
            continue
        n = per_provider.get(m["provider"], 0)
        if n >= 2:
            continue
        per_provider[m["provider"]] = n + 1
        out.append(m)
    return out


def runnable_t2v_plan(
    registry: Dict[str, Any], *, one_per_provider: bool = False
) -> List[Dict[str, Any]]:
    """Return only current-build routes capable of accepting a text prompt."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for model in flatten_models(registry):
        definition = registry.get(model["provider"]) or {}
        if not definition.get("handlerImplemented", True):
            continue
        if not is_text_to_video(model["qualified"]):
            continue
        if one_per_provider and model["provider"] in seen:
            continue
        seen.add(model["provider"])
        out.append(
            {
                **model,
                "rank": 0,
                "reason": "active-build implemented text-to-video handler",
                "handlerImplemented": True,
                "textToVideo": True,
            }
        )
    return sorted(out, key=lambda row: (row["provider"], row["model"]))


def _find_video_assets(node: Any, found: List[Dict[str, str]]) -> None:
    """Collect URL/base64 media without ever persisting live credential material."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                lk = k.lower()
                if lk in {"url", "video_url", "videourl", "uri", "gcsuri", "output"} and v.startswith(
                    ("http://", "https://", "gs://", "data:")
                ):
                    found.append({"kind": "url", "value": v})
                elif lk in {"b64_json", "bytesbase64encoded", "base64"} and len(v) > 64:
                    found.append({"kind": "base64", "value": v})
            else:
                _find_video_assets(v, found)
    elif isinstance(node, list):
        for v in node:
            _find_video_assets(v, found)


def _public_asset_ref(asset: Dict[str, str]) -> str:
    if asset["kind"] == "base64":
        return f"<base64 payload, {len(asset['value'])} chars>"
    return redact_url(asset["value"])


def local_backend_unavailable(base_url: str) -> bool:
    """Fail fast for a declared local engine that is not listening."""
    parsed = urlparse(base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2):
            return False
    except OSError:
        return True


def probe_model(
    session: requests.Session,
    qualified: str,
    duration: int,
    timeout: int,
    base_url: str = "",
) -> Dict[str, Any]:
    payload = {
        "model": qualified,
        "prompt": PROMPT,
        "duration": duration,
        "aspect_ratio": "16:9",
        "n": 1,
    }
    started = time.monotonic()
    if base_url and local_backend_unavailable(base_url):
        return {
            "model": qualified,
            "http_status": None,
            "elapsed": round(time.monotonic() - started, 1),
            "ok": False,
            "video_refs": [],
            "error": "LOCAL_BACKEND_UNAVAILABLE",
            "state": "LOCAL_BACKEND_UNAVAILABLE",
        }
    try:
        r = session.post(
            f"{OMNI_BASE}/v1/videos/generations",
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        return {
            "model": qualified,
            "http_status": None,
            "elapsed": round(time.monotonic() - started, 1),
            "ok": False,
            "video_refs": [],
            "error": f"{type(e).__name__}: {e}",
        }

    elapsed = round(time.monotonic() - started, 1)
    try:
        body: Any = r.json()
    except Exception:
        body = {"raw": r.text[:800]}

    assets: List[Dict[str, str]] = []
    _find_video_assets(body, assets)
    # Keep the live URLs in-process for byte verification, but persist only redacted
    # forms: a presigned OSS/S3/GCS query string is credential material (see redact_url).
    return {
        "model": qualified,
        "http_status": r.status_code,
        "elapsed": elapsed,
        "ok": r.status_code == 200 and bool(assets),
        "video_refs": [_public_asset_ref(asset) for asset in assets[:3]],
        "video_assets_live": assets[:3],
        "error": None if r.status_code == 200 else redact(json.dumps(body, default=str))[:400],
        "body_preview": redact(json.dumps(body, default=str))[:600],
    }


def verify_video_asset(asset: Dict[str, str], dest: Path) -> Dict[str, Any]:
    """Materialise a returned video asset and prove it is a real MP4, not just a 200.

    AGENTS.md forbids reporting something as working on the strength of a status code
    alone. A provider can return 200 with an error page, an empty object, or an expired
    link. So we fetch the asset, check the ISO-BMFF ``ftyp`` box at offset 4, and — when
    ffprobe is available — read back the real duration and resolution.
    """
    out: Dict[str, Any] = {"fetched": False, "assetKind": asset.get("kind")}
    try:
        if asset.get("kind") == "base64":
            data = base64.b64decode(asset.get("value", ""), validate=True)
            out["fetch_status"] = "inline"
        else:
            url = asset.get("value", "")
            if url.startswith("data:") and ";base64," in url:
                data = base64.b64decode(url.split(",", 1)[1], validate=True)
                out["fetch_status"] = "data-uri"
            else:
                client = requests.Session()
                client.trust_env = False
                r = client.get(
                    url,
                    timeout=180,
                    headers={"User-Agent": "omniroute-monetizer/1.0"},
                )
                out["fetch_status"] = r.status_code
                if r.status_code != 200:
                    return out
                data = r.content
        out["fetched"] = True
        out["bytes"] = len(data)
        if asset.get("kind") != "base64" and "r" in locals():
            out["content_type"] = r.headers.get("Content-Type")
        out["is_mp4"] = data[4:8] == b"ftyp"
        out["brand"] = data[8:12].decode("ascii", "replace")
        out["sha256"] = hashlib.sha256(data).hexdigest()
        if not out["is_mp4"]:
            return out
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        out["saved_to"] = str(dest)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        out["ffprobe"] = "not available"
        return out
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration:stream=codec_name,codec_type,width,height",
             "-of", "json", str(dest)],
            capture_output=True, text=True, timeout=90,
        )
        info = json.loads(proc.stdout or "{}")
        out["duration"] = round(float(info.get("format", {}).get("duration", 0) or 0), 2)
        for st in info.get("streams", []):
            if st.get("codec_type") == "video":
                out["video"] = f"{st.get('width')}x{st.get('height')} {st.get('codec_name')}"
            elif st.get("codec_type") == "audio":
                out["audio"] = str(st.get("codec_name"))
    except Exception as e:
        out["ffprobe_error"] = f"{type(e).__name__}: {e}"
    return out


def _read_report() -> Dict[str, Any]:
    try:
        value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _plan_key(plan: List[Dict[str, Any]]) -> List[str]:
    return [str(row["qualified"]) for row in plan]


def _write_progress(
    *,
    plan: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    started_at: str,
    state: str = "RUNNING",
) -> None:
    # Persist only redacted terminal rows.  The live asset values are removed
    # before this function is called, and presigned query strings never reach disk.
    working = [
        row["model"]
        for row in results
        if row.get("verification", {}).get("is_mp4") is True
    ]
    providers: Dict[str, int] = {}
    for model in working:
        provider = model.split("/", 1)[0]
        providers[provider] = providers.get(provider, 0) + 1
    report = {
        "schemaVersion": REPORT_SCHEMA,
        "state": state,
        "startedAt": started_at,
        "updatedAt": now(),
        "buildDist": str(DEFAULT_OMNIROUTE_DIST),
        "base_url": OMNI_BASE,
        "endpoint": "/v1/videos/generations",
        "planModels": _plan_key(plan),
        "probed": len(results),
        "working": working,
        "providerModelCapacity": dict(sorted(providers.items())),
        "results": results,
    }
    atomic_json(REPORT_PATH, report)
    atomic_json(
        ADMISSION_PATH,
        {
            "schemaVersion": 1,
            "generatedAt": now(),
            "sourceReport": str(REPORT_PATH),
            "endpoint": f"{OMNI_BASE}/v1/videos/generations",
            "entries": [
                {
                    "provider": row["model"].split("/", 1)[0],
                    "model": row["model"],
                    "modality": "video",
                    "state": "ADMITTED",
                    "proof": "DIRECT_VIDEO_MP4_OK",
                    "verifiedAt": row.get("verifiedAt") or now(),
                    "verification": row["verification"],
                }
                for row in results
                if row.get("verification", {}).get("is_mp4") is True
            ],
        },
    )


def _duration_error(result: Dict[str, Any]) -> bool:
    text = f"{result.get('error') or ''} {result.get('body_preview') or ''}".lower()
    return "duration" in text and any(word in text for word in ("between", "valid", "allowed", "range"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="probe every registry model, not the shortlist")
    ap.add_argument(
        "--runnable-all",
        action="store_true",
        help="probe every current-build implemented text-to-video model",
    )
    ap.add_argument(
        "--one-per-provider",
        action="store_true",
        help="probe one current-build text-to-video model per provider",
    )
    ap.add_argument("--plan-only", action="store_true", help="print the ranked plan and exit")
    ap.add_argument("--model", action="append", default=[], help="probe an explicit qualified model id")
    ap.add_argument("--duration", type=int, default=5, help="requested clip duration in seconds")
    ap.add_argument("--max", type=int, default=0, help="stop after N probes (0 = no limit)")
    ap.add_argument("--timeout", type=int, default=GEN_TIMEOUT, help="per-request timeout in seconds")
    ap.add_argument("--no-verify", action="store_true", help="skip downloading and ffprobing the result")
    ap.add_argument("--fresh", action="store_true", help="ignore a prior resumable report")
    args = ap.parse_args()

    if not args.plan_only and not args.model and os.environ.get("OMNI_VIDEO_CONFIRM_SPEND") != "1":
        ap.error("video generation is spend-gated; set OMNI_VIDEO_CONFIRM_SPEND=1")

    registry = annotate_supported(load_registry("VIDEO_PROVIDERS"))
    unwired = sorted(p for p, d in registry.items() if not d.get("handlerImplemented", True))
    print(f"[*] VIDEO_PROVIDERS registry: {len(registry)} providers, {len(flatten_models(registry))} models")
    if unwired:
        print(f"[!] {len(unwired)} registered providers have NO handler and always 400: {', '.join(unwired)}")

    api = OmniRouteAPI(base_url=OMNI_BASE)
    api.session.trust_env = False
    # Deliberately not using api.login(): its 15s timeout flakes against ~9.5s bcrypt.
    resp = api.session.post(
        f"{api.api}/auth/login", json={"password": api._password}, timeout=LOGIN_TIMEOUT
    )
    if resp.status_code != 200:
        print(f"[-] management login failed: HTTP {resp.status_code}")
        return 2
    api._logged_in = True
    print("[+] management login OK")

    if args.model:
        plan = [
            {"qualified": m, "provider": m.split("/", 1)[0], "model": m.split("/", 1)[-1],
             "rank": -1, "reason": "explicitly requested", "authType": "", "format": ""}
            for m in args.model
        ]
    elif args.runnable_all or args.one_per_provider:
        # The broad media proof does not need `/api/providers`.  That endpoint
        # refreshes every chat-provider model cache and was the reason the old
        # all-model worker could sit indefinitely before its first video call.
        plan = runnable_t2v_plan(registry, one_per_provider=args.one_per_provider)
    else:
        try:
            connections = api.get_connections()
        except Exception as exc:
            print(f"[-] provider inventory unavailable: {type(exc).__name__}: {exc}")
            return 2
        print(f"[+] {len(connections)} provider connections")
        plan = build_plan(registry, connections, shortlist=not args.all)

    if args.max:
        plan = plan[: args.max]

    print(f"\n[*] probe plan ({len(plan)} candidates, cheapest-first):")
    for m in plan:
        print(f"    rank{m['rank']}  {m['qualified']:52} {m['reason']}")

    if args.plan_only:
        atomic_json(
            PLAN_PATH,
            {
                "schemaVersion": 1,
                "generatedAt": now(),
                "buildDist": str(DEFAULT_OMNIROUTE_DIST),
                "strategy": "runnable_t2v" if (args.runnable_all or args.one_per_provider) else "ranked_registry",
                "count": len(plan),
                "models": plan,
            },
        )
        return 0

    print(f"\n[*] probing POST {OMNI_BASE}/v1/videos/generations (timeout {args.timeout}s) ...\n", flush=True)
    prior = {} if args.fresh else _read_report()
    if prior.get("schemaVersion") == REPORT_SCHEMA and prior.get("planModels") == _plan_key(plan):
        prior_results = {
            str(row.get("model")): row
            for row in prior.get("results", [])
            if isinstance(row, dict) and row.get("model")
        }
    else:
        prior_results = {}
    # Seed the in-memory result set with current-plan terminal rows before the
    # first progress write.  If the process is interrupted after startup, the
    # durable file still contains all prior completed work.
    results: List[Dict[str, Any]] = [
        prior_results[m["qualified"]]
        for m in plan
        if prior_results.get(m["qualified"], {}).get("terminal") is True
    ]
    started_at = now()
    _write_progress(plan=plan, results=[], started_at=started_at, state="RUNNING")
    for m in plan:
        old = prior_results.get(m["qualified"])
        if old and old.get("terminal") is True:
            results.append(old)
            print(f"  [RESUME] {m['qualified']:48} {old.get('state')}", flush=True)
            continue

        durations = [args.duration]
        res = probe_model(
            api.session, m["qualified"], durations[0], args.timeout, m.get("baseUrl", "")
        )
        attempts = [{"duration": durations[0], "http_status": res.get("http_status"), "error": res.get("error")}]
        if _duration_error(res):
            durations.extend(d for d in DURATION_FALLBACKS if d not in durations)
            for duration in durations[1:]:
                retry = probe_model(
                    api.session, m["qualified"], duration, args.timeout, m.get("baseUrl", "")
                )
                attempts.append({"duration": duration, "http_status": retry.get("http_status"), "error": retry.get("error")})
                res = retry
                if res.get("ok") or not _duration_error(res):
                    break
        res["attempts"] = attempts
        res["rank"] = m["rank"]
        res["reason"] = m["reason"]
        res["terminal"] = True
        results.append(res)
        mark = "PASS" if res["ok"] else "FAIL"
        detail = res["video_refs"][0][:90] if res["video_refs"] else (res["error"] or "")[:150]
        print(f"  [{mark}] {m['qualified']:48} HTTP {str(res['http_status']):5} {res['elapsed']:>6}s  {detail}", flush=True)

        # A 200 is not proof. Fetch the asset and confirm real MP4 bytes.
        if res["ok"] and not args.no_verify:
            dest = STATE_DIR / "clips" / (m["qualified"].replace("/", "_") + ".mp4")
            v = verify_video_asset(res.pop("video_assets_live")[0], dest)
            res["verification"] = v
            if v.get("is_mp4"):
                res["state"] = "DIRECT_VIDEO_MP4_OK"
                res["verifiedAt"] = now()
                print(
                    f"         verified: {v.get('bytes'):,} bytes, {v.get('duration')}s, "
                    f"{v.get('video')}, audio={v.get('audio')}"
                , flush=True)
            else:
                res["ok"] = False
                res["state"] = "ASSET_NOT_MP4"
                print(f"         NOT a valid MP4: {v}", flush=True)
        elif res["ok"]:
            res["ok"] = False
            res["state"] = "UNVERIFIED_HTTP_200"
        else:
            res["state"] = "HTTP_OR_PROVIDER_FAILURE"

        res.pop("video_assets_live", None)
        _write_progress(plan=plan, results=results, started_at=started_at, state="RUNNING")

    _write_progress(plan=plan, results=results, started_at=started_at, state="COMPLETE")
    working = [r for r in results if r.get("verification", {}).get("is_mp4") is True]
    path = REPORT_PATH
    print(f"\n[*] {len(working)}/{len(results)} candidates returned a usable video payload")
    print(f"[*] full results -> {path}")
    if working:
        print("[+] WORKING VIDEO MODELS:")
        for r in working:
            print(f"      {r['model']}  ({r['elapsed']}s)  {r['video_refs'][0][:100]}", flush=True)
        return 0
    print("[-] no working video model yet")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
