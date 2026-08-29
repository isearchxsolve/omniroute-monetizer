#!/usr/bin/env python3
"""Ask each harvested jar whether its seat has VIDEO entitlement -- read-only, no spend.

Why this exists
---------------
Video is the scarce supply. A 3-hour film needs ~2,160 clips and capacity sits at ~3, so the whole
project is gated on video seats. Meanwhile 18 jars sit in state/secrets/ and the video pool speaks
exactly three providers (digen.ai, rtst.ai, Google Flow). Several already-harvested jars belong to
providers that ship video models -- Qwen ships Wan, Zhipu ships CogVideoX, Doubao ships Seedance,
1min.AI and Monica aggregate Kling/Runway -- and not one of them has ever been asked about video.

Each jar carries `modality: "chat"`. That field was set by the capture that made it, and it records
what the seat was *probed for*, not what the seat *can do*. Reading it as a capability is this repo's
signature defect: a verdict trusted for a layer it never measured. This tool measures the other layer.

What it does, precisely
-----------------------
For each jar it derives the API origin from the recorded exchange, then issues **GET requests only**
against conventional read-only surfaces (model list, user, credits, features, config) carrying the
harvested cookie header. It scans each response for video-generation vocabulary and reports what it
found, with the path that proved it.

What it deliberately does NOT do
--------------------------------
* **No generation.** Never submits a job, so it can never consume a credit. `nextAction` on every
  video tab in the graduation manifest is `video_contract_and_spend_gate`; this runs entirely before
  that gate.
* **No reconstruction.** It does not synthesise a generate call from a guessed schema. Reconstruction
  gets gated -- the omni way is to replay a recorded genuine exchange. Producing a *generation*
  contract still requires a real captured video exchange, which is the harvester's lane. This tool
  only answers which seats are worth that expensive capture.
* **No writes to any jar**, and no secret ever reaches stdout or the report. Cookie headers are
  measured by length only.

Politeness
----------
These are free accounts on other people's services. Requests are serialised with a delay, capped per
host, and a host stops as soon as a strong signal is found. GET traffic on a live jar is also mildly
protective -- an idle session is the one that dies.

Reading the verdict
-------------------
    ENTITLED    a strong signal (a named video model or an explicit t2v/i2v capability)
    LIKELY      only weak signals (the word "video", mp4, fps) -- could be playback, not generation
    NONE        authenticated and reachable, nothing about video
    NO_AUTH     every surface returned 401/403 -- the jar is stale for this origin
    UNREACHABLE nothing answered

ENTITLED is a claim about *entitlement*, not about a working contract. It means: capture this tab
next. It does not mean the seat can serve a job yet.

    python scripts/automation/probe_video_entitlement.py
    python scripts/automation/probe_video_entitlement.py --hosts chat.qwen.ai,app.1min.ai
    python scripts/automation/probe_video_entitlement.py --list
"""
from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRETS = ROOT / "state" / "secrets"
OUT = ROOT / "state" / "video_entitlement.json"

# Conventional read-only surfaces. A 404 costs nothing and tells us nothing, which is fine -- the
# point is to find the one that answers. Ordered cheapest-and-most-likely first so a strong hit
# short-circuits before the rest are tried.
PROBE_PATHS = (
    "/api/models",
    "/api/v1/models",
    "/api/v2/models",
    "/api/config",
    "/api/features",
    "/api/user",
    "/api/me",
    "/api/credits",
)

# A named video model or an explicit modality flag. These do not appear by accident.
STRONG = (
    "text-to-video", "image-to-video", "t2v", "i2v", "txt2video", "img2video",
    "wan2", "wanx", "wan-", "cogvideo", "seedance", "pixeldance", "kling",
    "runway", "gen-3", "gen3", "veo-", "veo2", "veo3", "sora", "hailuo",
    "minimax-video", "pika", "luma", "dreamina", "vidu", "video_generation",
    "videogeneration", "video-generation", "video_model", "generate_video",
)
# Could equally be a video *player*, an upload field, or a TTS duration. Reported, never trusted.
WEAK = ("\"video\"", "'video'", "video:", "mp4", "webm", "fps", "aspect_ratio", "duration_seconds")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")
# Headers worth inheriting from the recorded exchange -- they are what made the seat accept the
# request in the first place. Anything body-shaped or hop-by-hop is dropped.
INHERIT = ("authorization", "x-request-id", "x-csrf-token", "x-api-key", "bx-v", "source",
           "x-accel-buffering", "referer", "origin", "accept-language", "x-app-version",
           "x-requested-with", "baggage", "sentry-trace", "authority", "version")
DROP = ("content-type", "content-length", "accept-encoding", "connection", "host",
        "transfer-encoding", "cookie", "te", "upgrade")

DELAY_S = 1.2          # between requests to one host
HOST_DELAY_S = 2.0     # between hosts
TIMEOUT_S = 15
MAX_BYTES = 400_000    # a model list is small; a HTML shell is not worth reading further


def load_jars(only: set[str] | None) -> list[dict]:
    jars = []
    for path in sorted(SECRETS.glob("session_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"  skip {path.name}: unreadable ({exc.__class__.__name__})")
            continue
        host = data.get("host") or ""
        if not host or (only and host not in only):
            continue
        rec = data.get("recorded_exchange") or {}
        cookie = data.get("cookie_header") or rec.get("cookie_header") or ""
        url = rec.get("url") or ""
        if not cookie or not url:
            print(f"  skip {host}: no cookie header or no recorded exchange to derive an origin from")
            continue
        jars.append({
            "file": path.name,
            "host": host,
            "site": data.get("site") or host,
            "modality": data.get("modality") or "",
            "alive": bool((data.get("status") or {}).get("alive")),
            "cookie": cookie,
            "cookie_bytes": len(cookie),
            "origin": f"{urllib.parse.urlsplit(url).scheme}://{urllib.parse.urlsplit(url).netloc}",
            "headers": {k.lower(): v for k, v in (rec.get("request_headers") or {}).items()
                        if k.lower() in INHERIT and k.lower() not in DROP},
        })
    return jars


def fetch(url: str, jar: dict) -> tuple[int, str]:
    """GET url with the harvested auth. Returns (status, body-or-error-token)."""
    headers = {"user-agent": UA, "accept": "application/json, text/plain, */*",
               "accept-encoding": "gzip, identity", "cookie": jar["cookie"]}
    headers.update(jar["headers"])
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read(MAX_BYTES)
            if (resp.headers.get("content-encoding") or "").lower() == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(MAX_BYTES)
        except Exception:
            raw = b""
        return exc.code, raw.decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"__ERR__{exc.__class__.__name__}"


def scan(body: str) -> tuple[list[str], list[str]]:
    low = body.lower()
    return ([s for s in STRONG if s in low], [w for w in WEAK if w in low])


def is_html_shell(body: str) -> bool:
    head = body[:400].lower()
    return "<!doctype" in head or "<html" in head


def probe(jar: dict) -> dict:
    row = {"host": jar["host"], "site": jar["site"], "file": jar["file"],
           "recordedModality": jar["modality"], "jarAlive": jar["alive"],
           "cookieBytes": jar["cookie_bytes"], "origin": jar["origin"],
           "verdict": "UNREACHABLE", "strong": [], "weak": [], "evidencePath": None,
           "surfaces": []}
    saw_auth_ok = saw_any = False
    for path in PROBE_PATHS:
        status, body = fetch(jar["origin"] + path, jar)
        note = ""
        if body.startswith("__ERR__"):
            note = body[7:]
        elif is_html_shell(body):
            note = "html-shell"
        row["surfaces"].append({"path": path, "status": status, "bytes": len(body), "note": note})
        if status:
            saw_any = True
        if status in (401, 403):
            time.sleep(DELAY_S)
            continue
        if status == 200 and not is_html_shell(body):
            saw_auth_ok = True
            strong, weak = scan(body)
            if strong or weak:
                row["strong"] = sorted(set(row["strong"]) | set(strong))
                row["weak"] = sorted(set(row["weak"]) | set(weak))
                row["evidencePath"] = row["evidencePath"] or path
            if strong:
                break                      # strong signal -- stop knocking on this seat
        time.sleep(DELAY_S)

    if row["strong"]:
        row["verdict"] = "ENTITLED"
    elif row["weak"]:
        row["verdict"] = "LIKELY"
    elif saw_auth_ok:
        row["verdict"] = "NONE"
    elif saw_any:
        row["verdict"] = "NO_AUTH"
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hosts", help="comma-separated hosts to probe (default: every jar)")
    ap.add_argument("--list", action="store_true", help="show what would be probed, send nothing")
    args = ap.parse_args()

    only = {h.strip() for h in args.hosts.split(",")} if args.hosts else None
    jars = load_jars(only)
    if not jars:
        print("no jar had both a cookie header and a recorded exchange")
        return 1

    print(f"jars: {len(jars)}   surfaces/host: {len(PROBE_PATHS)}   GET only, no generation, no spend")
    if args.list:
        for j in jars:
            print(f"  {j['host']:26} {j['origin']:38} modality={j['modality'] or '-':6} "
                  f"cookie={j['cookie_bytes']}B")
        return 0

    rows = []
    for index, jar in enumerate(jars, 1):
        print(f"[{index}/{len(jars)}] {jar['host']}", flush=True)
        row = probe(jar)
        rows.append(row)
        ev = f"  via {row['evidencePath']}" if row["evidencePath"] else ""
        hits = ", ".join(row["strong"][:5]) or ", ".join(row["weak"][:4]) or "-"
        print(f"    {row['verdict']:12} {hits}{ev}")
        time.sleep(HOST_DELAY_S)

    order = {"ENTITLED": 0, "LIKELY": 1, "NONE": 2, "NO_AUTH": 3, "UNREACHABLE": 4}
    rows.sort(key=lambda r: (order[r["verdict"]], r["host"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generatedAt": int(time.time()),
        "method": "read-only GET against the seat's own API surfaces with the harvested cookie header",
        "disclaimer": "ENTITLED means capture this tab next. It is NOT a working generation contract: "
                      "that still needs a recorded genuine video exchange (harvester's lane).",
        "counts": {v: sum(1 for r in rows if r["verdict"] == v) for v in order},
        "results": rows,
    }, indent=2) + "\n", encoding="utf-8")

    print()
    for verdict in order:
        hosts = [r["host"] for r in rows if r["verdict"] == verdict]
        if hosts:
            print(f"{verdict:12} {len(hosts):2}  {' '.join(hosts)}")
    print(f"\nreport: {OUT.relative_to(ROOT)}")
    entitled = [r for r in rows if r["verdict"] == "ENTITLED"]
    if entitled:
        print("\nCapture these next -- the jar is already harvested, so only the video exchange is missing:")
        for r in entitled:
            print(f"  {r['site']:28} {r['host']:24} {', '.join(r['strong'][:4])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
