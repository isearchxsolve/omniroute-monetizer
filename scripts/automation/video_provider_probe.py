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
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from omniroute_api import BASE_URL, STATE_DIR, OmniRouteAPI, redact, redact_url, save_json  # noqa: E402
from video_registry import annotate_supported, flatten_models, load_registry  # noqa: E402

# Login is bcrypt-bound and measured at ~9.5s on this host; the shared client's 15s
# ceiling is too tight and flakes. Probing must never fail for that reason.
LOGIN_TIMEOUT = 120

# A video request is a real generation job, and dashscope-class providers are async
# (submit + poll a task url) so the router can hold the connection for minutes.
# Overridable per-run: reachability probes want it short, real renders want it long.
GEN_TIMEOUT = 150

# Models that cannot be driven by a text prompt alone. The router rejects these with
# "Image input is required" / "Video input is required", which is a correct response to
# a malformed request, not a provider fault — so they are worthless as health probes.
# The Animator is text-to-video, so these are out of scope for the pipeline anyway.
NON_T2V_MARKERS = ("i2v", "r2v", "image-to-video", "videoedit", "video-edit", "-ref", "ti2v")

PROMPT = (
    "A slow cinematic dolly-in on a lone astronaut standing at the edge of a vast "
    "red canyon at golden hour, dust drifting through low sunlight, shot on 35mm."
)


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


def _find_video_urls(node: Any, found: List[str]) -> None:
    """Walk a response body collecting anything that looks like a video reference."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                lk = k.lower()
                if lk in {"url", "video_url", "videourl", "uri", "gcsuri", "output"} and v.startswith(
                    ("http://", "https://", "gs://", "data:")
                ):
                    found.append(v)
                elif lk in {"b64_json", "bytesbase64encoded", "base64"} and len(v) > 64:
                    found.append(f"<base64 payload, {len(v)} chars>")
            else:
                _find_video_urls(v, found)
    elif isinstance(node, list):
        for v in node:
            _find_video_urls(v, found)


def probe_model(session: requests.Session, qualified: str, duration: int, timeout: int) -> Dict[str, Any]:
    payload = {
        "model": qualified,
        "prompt": PROMPT,
        "duration": duration,
        "aspect_ratio": "16:9",
        "n": 1,
    }
    started = time.monotonic()
    try:
        r = session.post(
            f"{BASE_URL}/v1/videos/generations",
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

    refs: List[str] = []
    _find_video_urls(body, refs)
    # Keep the live URLs in-process for byte verification, but persist only redacted
    # forms: a presigned OSS/S3/GCS query string is credential material (see redact_url).
    return {
        "model": qualified,
        "http_status": r.status_code,
        "elapsed": elapsed,
        "ok": r.status_code == 200 and bool(refs),
        "video_refs": [redact_url(u) for u in refs[:3]],
        "video_refs_live": refs[:3],
        "error": None if r.status_code == 200 else redact(json.dumps(body, default=str))[:400],
        "body_preview": redact(json.dumps(body, default=str))[:600],
    }


def verify_video_bytes(url: str, dest: Path) -> Dict[str, Any]:
    """Download a returned video URL and prove it is a real MP4, not just a 200.

    AGENTS.md forbids reporting something as working on the strength of a status code
    alone. A provider can return 200 with an error page, an empty object, or an expired
    link. So we fetch the asset, check the ISO-BMFF ``ftyp`` box at offset 4, and — when
    ffprobe is available — read back the real duration and resolution.
    """
    out: Dict[str, Any] = {"fetched": False}
    try:
        r = requests.get(url, timeout=180, headers={"User-Agent": "omniroute-monetizer/1.0"})
        out["fetch_status"] = r.status_code
        if r.status_code != 200:
            return out
        data = r.content
        out["fetched"] = True
        out["bytes"] = len(data)
        out["content_type"] = r.headers.get("Content-Type")
        out["is_mp4"] = data[4:8] == b"ftyp"
        out["brand"] = data[8:12].decode("ascii", "replace")
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="probe every registry model, not the shortlist")
    ap.add_argument("--plan-only", action="store_true", help="print the ranked plan and exit")
    ap.add_argument("--model", action="append", default=[], help="probe an explicit qualified model id")
    ap.add_argument("--duration", type=int, default=5, help="requested clip duration in seconds")
    ap.add_argument("--max", type=int, default=0, help="stop after N probes (0 = no limit)")
    ap.add_argument("--timeout", type=int, default=GEN_TIMEOUT, help="per-request timeout in seconds")
    ap.add_argument("--no-verify", action="store_true", help="skip downloading and ffprobing the result")
    args = ap.parse_args()

    registry = annotate_supported(load_registry("VIDEO_PROVIDERS"))
    unwired = sorted(p for p, d in registry.items() if not d.get("handlerImplemented", True))
    print(f"[*] VIDEO_PROVIDERS registry: {len(registry)} providers, {len(flatten_models(registry))} models")
    if unwired:
        print(f"[!] {len(unwired)} registered providers have NO handler and always 400: {', '.join(unwired)}")

    api = OmniRouteAPI()
    # Deliberately not using api.login(): its 15s timeout flakes against ~9.5s bcrypt.
    resp = api.session.post(
        f"{api.api}/auth/login", json={"password": api._password}, timeout=LOGIN_TIMEOUT
    )
    if resp.status_code != 200:
        print(f"[-] management login failed: HTTP {resp.status_code}")
        return 2
    api._logged_in = True
    print("[+] management login OK")

    connections = api.get_connections()
    print(f"[+] {len(connections)} provider connections")

    if args.model:
        plan = [
            {"qualified": m, "provider": m.split("/", 1)[0], "model": m.split("/", 1)[-1],
             "rank": -1, "reason": "explicitly requested", "authType": "", "format": ""}
            for m in args.model
        ]
    else:
        plan = build_plan(registry, connections, shortlist=not args.all)

    if args.max:
        plan = plan[: args.max]

    print(f"\n[*] probe plan ({len(plan)} candidates, cheapest-first):")
    for m in plan:
        print(f"    rank{m['rank']}  {m['qualified']:52} {m['reason']}")

    if args.plan_only:
        save_json("video_probe_plan.json", plan)
        return 0

    print(f"\n[*] probing POST {BASE_URL}/v1/videos/generations (timeout {args.timeout}s) ...\n")
    results: List[Dict[str, Any]] = []
    for m in plan:
        res = probe_model(api.session, m["qualified"], args.duration, args.timeout)
        res["rank"] = m["rank"]
        res["reason"] = m["reason"]
        results.append(res)
        mark = "PASS" if res["ok"] else "FAIL"
        detail = res["video_refs"][0][:90] if res["video_refs"] else (res["error"] or "")[:150]
        print(f"  [{mark}] {m['qualified']:48} HTTP {str(res['http_status']):5} {res['elapsed']:>6}s  {detail}")

        # A 200 is not proof. Fetch the asset and confirm real MP4 bytes.
        if res["ok"] and not args.no_verify:
            dest = STATE_DIR / "clips" / (m["qualified"].replace("/", "_") + ".mp4")
            v = verify_video_bytes(res.pop("video_refs_live")[0], dest)
            res["verification"] = v
            if v.get("is_mp4"):
                print(
                    f"         verified: {v.get('bytes'):,} bytes, {v.get('duration')}s, "
                    f"{v.get('video')}, audio={v.get('audio')}"
                )
            else:
                res["ok"] = False
                print(f"         NOT a valid MP4: {v}")

    # Never persist live presigned URLs (see redact_url).
    for res in results:
        res.pop("video_refs_live", None)

    working = [r for r in results if r["ok"]]
    path = save_json(
        "video_provider_probe.json",
        {
            "base_url": BASE_URL,
            "endpoint": "/v1/videos/generations",
            "probed": len(results),
            "working": [r["model"] for r in working],
            "results": results,
        },
    )
    print(f"\n[*] {len(working)}/{len(results)} candidates returned a usable video payload")
    print(f"[*] full results -> {path}")
    if working:
        print("[+] WORKING VIDEO MODELS:")
        for r in working:
            print(f"      {r['model']}  ({r['elapsed']}s)  {r['video_refs'][0][:100]}")
        return 0
    print("[-] no working video model yet")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
