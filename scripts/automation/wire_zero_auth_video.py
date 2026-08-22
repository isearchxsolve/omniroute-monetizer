"""Wire OmniRoute's zero-auth video providers and try to produce an actual video file.

Why this exists
---------------
`video_registry.py` reads OmniRoute's COMPILED build (not its API, which does not expose this)
and reports two different things:

  * VIDEO_PROVIDERS  -- 22 providers / 83 models that the build *declares*.
  * supported_video_formats() -- the 15 formats whose handler is actually *implemented*.

Only the intersection can ever return a video. Measured 2026-08-22, three of the implemented
providers need no credential at all:

    veoaifree-web   auth=none   baseUrl https://veoaifree.com/wp-admin/admin-ajax.php
                                models: veo (VEO 3.1), seedance
    comfyui         auth=none   baseUrl http://localhost:8188   models: animatediff, svd-xt
    sdwebui         auth=none   baseUrl http://localhost:7860   models: animatediff-webui

comfyui and sdwebui are LOCAL engines; neither port was listening on this box, so they cannot
work until that software is installed and running. veoaifree-web is a public free service and
needs nothing but a connection row -- and OmniRoute had NO connection row for any of the nine
handler-backed video providers (veoaifree-web, comfyui, sdwebui, leonardo, haiper,
adobe-firefly, xai, googleflow, runwayml). That missing row, not money, is what blocks it.

Honesty rules this script follows
---------------------------------
* A video is only reported as produced if the bytes actually start with an MP4 `ftyp` box
  (bytes[4:8] == b"ftyp"). File size alone proves nothing.
* Exact upstream HTTP codes and error text are printed, never paraphrased.
* Nothing is deleted; no existing connection is modified. Only new rows are added.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = "http://localhost:20128"
OUT = ROOT / "state" / "video_out"

# provider id -> (display name, first model id to try)
ZERO_AUTH = {
    "veoaifree-web": ("VeoAIFree (zero-auth web video)", ["veo", "seedance"]),
    "comfyui": ("ComfyUI (local, zero-auth)", ["svd-xt", "animatediff"]),
    "sdwebui": ("SD WebUI (local, zero-auth)", ["animatediff-webui"]),
}

PROMPT = "A calm ocean wave at sunrise, cinematic"


def create_connection(api: OmniRouteAPI, provider: str, name: str) -> dict:
    """POST /api/providers. Tries a few body shapes because the create schema is not documented."""
    attempts = [
        {"provider": provider, "authType": "none", "name": name, "isActive": True, "priority": 50},
        {"provider": provider, "authType": "none", "name": name, "isActive": True},
        {"provider": provider, "name": name, "isActive": True},
        {"provider": provider, "authType": "none", "name": name, "apiKey": "", "isActive": True},
    ]
    last = {}
    for i, body in enumerate(attempts, 1):
        r = api.session.post(f"{api.api}/providers", json=body, timeout=30)
        try:
            js = r.json()
        except Exception:
            js = {"raw": r.text[:300]}
        last = {"attempt": i, "http": r.status_code, "body": js, "sent_keys": list(body)}
        print(f"    POST attempt {i}: HTTP {r.status_code}  {json.dumps(js)[:220]}")
        if r.status_code in (200, 201):
            return last
    return last


def try_video(model: str, timeout: int = 600) -> dict:
    """POST /v1/videos/generations and report exactly what came back."""
    url = f"{BASE}/v1/videos/generations"
    try:
        r = requests.post(url, json={"model": model, "prompt": PROMPT, "duration": 5}, timeout=timeout)
    except Exception as exc:
        return {"model": model, "ok": False, "detail": f"request failed: {type(exc).__name__}: {exc}"}

    if r.status_code >= 400:
        return {"model": model, "ok": False, "http": r.status_code, "detail": r.text[:500]}

    # Success shape varies: raw bytes, {url}, or {b64_json}.
    ctype = r.headers.get("content-type", "")
    data = None
    if "application/json" in ctype:
        js = r.json()
        blob = json.dumps(js)[:400]
        for key in ("b64_json", "b64", "video_b64"):
            found = _deep_get(js, key)
            if found:
                data = base64.b64decode(found)
                break
        if data is None:
            link = _deep_get(js, "url") or _deep_get(js, "video_url")
            if link:
                try:
                    dl = requests.get(link, timeout=timeout)
                    if dl.status_code == 200:
                        data = dl.content
                except Exception as exc:
                    return {"model": model, "ok": False, "http": 200,
                            "detail": f"got url but download failed: {type(exc).__name__}"}
        if data is None:
            return {"model": model, "ok": False, "http": 200,
                    "detail": f"200 but no video bytes/url in body: {blob}"}
    else:
        data = r.content

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{model.replace('/', '_')}.mp4"
    path.write_bytes(data)
    ftyp = len(data) > 8 and data[4:8] == b"ftyp"
    return {"model": model, "ok": ftyp, "http": 200, "bytes": len(data), "path": str(path),
            "detail": "REAL MP4 (ftyp box present)" if ftyp
                      else f"NOT a valid MP4; first 16 bytes = {data[:16]!r}"}


def _deep_get(obj, key):
    if isinstance(obj, dict):
        if key in obj and obj[key]:
            return obj[key]
        for v in obj.values():
            got = _deep_get(v, key)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _deep_get(v, key)
            if got:
                return got
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="", help="comma-separated subset of zero-auth providers")
    ap.add_argument("--no-create", action="store_true", help="skip creating rows; just try video")
    args = ap.parse_args()

    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(ZERO_AUTH)

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("[-] OmniRoute login failed -- nothing changed")
        return 2

    existing = {str(c.get("provider", "")).lower(): c for c in api.get_connections()}
    results = []

    for prov in names:
        disp, models = ZERO_AUTH[prov]
        print(f"\n=== {prov} ===")
        if prov in existing:
            c = existing[prov]
            print(f"    connection already exists id={c.get('id')} active={c.get('isActive')}")
        elif args.no_create:
            print("    no connection row and --no-create given; skipping create")
        else:
            print("    no connection row -> creating")
            create_connection(api, prov, disp)

        for m in models:
            model = f"{prov}/{m}"
            print(f"    -> generating {model}")
            res = try_video(model)
            results.append(res)
            flag = "REAL VIDEO" if res.get("ok") else "no"
            print(f"       {flag}: HTTP {res.get('http','-')} {res.get('detail','')[:300]}")
            if res.get("ok"):
                break

    print("\n" + "=" * 70)
    wins = [r for r in results if r.get("ok")]
    print(f"verified MP4s produced: {len(wins)} of {len(results)} attempts")
    for r in wins:
        print(f"   {r['model']}  {r['bytes']} bytes  -> {r['path']}")
    if not wins:
        print("   none. Nothing is claimed as working.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
