"""inspect_recorded_job.py — read a recorded_job capture OFFLINE and print its SHAPE only.

record_video_job.py writes the full wire (cookies, tokens, bodies) into the gitignored secret
state/secrets/session_<host>.json. This reads that file and prints ONLY structure: endpoints, JSON
key paths, value TYPES, and a few whitelisted non-secret scalars (status codes, credit counts, job
ids, media urls). It never prints a cookie, an authorization header, or any unrecognised string
value — strings are reduced to "str[len]" unless the key is on the safe list.

    python inspect_recorded_job.py --host digen.ai
      --seq 13            deep-dive one exchange (full key tree of req + resp)
      --show-values       additionally print values for SAFE keys only (ids, urls, counts, codes)
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
from typing import Any

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")

# keys whose values are safe to show (no auth material): ids, statuses, counts, timings.
# camelCase-aware: the token may follow a lowercase char ("videoUrl", "queueId") and may carry a
# trailing version suffix ("videoURLV1").
_SAFE_KEY = re.compile(
    r"(?:^|_|(?<=[a-z0-9]))(id|ids|status|state|code|msg|message|"
    r"credit|credits|remain|balance|count|total|num|amount|cost|price|point|points|duration|"
    r"width|height|resolution|ratio|fps|model|type|kind|name|title|progress|percent|queue|"
    r"created|updated|finish|time|ts|seconds|error|reason|scene|task|job|prompt|seed|ecode|"
    r"engine|strength|lipsync|public|generate|upscale|aspect|tags|activity|level|plan|tier|expire)"
    r"(?:v\d+)?$", re.I)
# url-ish keys: rendered host + extension only — a media URL can carry a signed query/token
_URL_KEY = re.compile(r"(?:^|_|(?<=[a-z0-9]))(url|uri|link|src|cover|thumb|thumbnail|"
                      r"video|audio|image|poster)(?:v\d+)?$", re.I)
_SECRET_KEY = re.compile(r"(cookie|auth|token|secret|password|passwd|sign|signature|key|jwt|"
                         r"session|bearer|nonce|csrf)", re.I)


def _render_url(s: str) -> str:
    """host + last path segment's extension + whether a query/signature rides along."""
    if not s:
        return 'url:""'
    m = re.match(r"^(https?)://([^/?#]+)([^?#]*)(\?.*)?$", s)
    if not m:
        return f"url-ish str[{len(s)}]"
    scheme, host, path, query = m.group(1), m.group(2), m.group(3) or "", m.group(4) or ""
    ext = re.search(r"(\.[A-Za-z0-9]{2,5})$", path)
    depth = len([p for p in path.split("/") if p])
    return (f"{scheme}://{host}/…[{depth} seg]{ext.group(1) if ext else ''}"
            f"{'  +QUERY(signed?) ' + str(len(query)) + 'ch' if query else '  (no query)'}"
            f"  total={len(s)}ch")


def _scalar(k: str, v: Any, show: bool) -> str:
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return json.dumps(v)
    s = str(v)
    if _SECRET_KEY.search(k or ""):
        return f"<withheld str[{len(s)}]>"
    if _URL_KEY.search(k or ""):
        return _render_url(s) if s else 'url:""'
    if show and _SAFE_KEY.search(k or "") and len(s) <= 300:
        return json.dumps(s)
    return f"str[{len(s)}]"


def walk(node: Any, show: bool, key: str = "", prefix: str = "", depth: int = 0, crack: bool = True) -> None:
    pad = "  " * depth
    if isinstance(node, dict):
        print(f"{pad}{prefix or '{}'}")
        for k, v in list(node.items())[:40]:
            walk(v, show, key=k, prefix=f"{k}:", depth=depth + 1, crack=crack)
    elif isinstance(node, list):
        print(f"{pad}{prefix} [list len={len(node)}]")
        if node:
            walk(node[0], show, key=key, prefix="[0]:", depth=depth + 1, crack=crack)
    else:
        # a JSON-encoded string field (digen packs scene_params / data this way) — crack it open
        if crack and isinstance(node, str) and len(node) > 20 and not _SECRET_KEY.search(key or ""):
            inner = _maybe_json(node)
            if isinstance(inner, (dict, list)):
                print(f"{pad}{prefix} <json-string, {len(node)}ch> ->")
                walk(inner, show, key=key, prefix="", depth=depth + 1, crack=crack)
                return
        print(f"{pad}{prefix} {_scalar(key, node, show)}")


def _maybe_json(s: Any):
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--seq", type=int, default=None)
    ap.add_argument("--show-values", action="store_true")
    ap.add_argument("--api-only", action="store_true", help="only exchanges whose host starts with api.")
    a = ap.parse_args()

    path = SECRETS / f"session_{a.host.replace('.', '_')}.json"
    if not path.exists():
        print(f"no capture at {path}")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    job = (data.get("recorded_job") or {}).get("exchanges") or []
    if not job:
        print("no recorded_job in this secret")
        return 1
    print(f"[inspect] {a.host}: {len(job)} exchanges (values withheld unless --show-values + safe key)\n")

    if a.seq is not None:
        e = next((x for x in job if x["seq"] == a.seq), None)
        if not e:
            print(f"no exchange seq={a.seq}")
            return 1
        print(f"=== seq {e['seq']}  {e['method']} {e['url']}")
        print(f"    status={e.get('status')} mime={e.get('mimeType')} t+{e.get('ts_rel')}s")
        hdrs = {k: v for k, v in (e.get("request_headers") or {}).items()}
        print(f"    request header NAMES: {sorted(hdrs)}")
        rb = _maybe_json(e.get("request_body"))
        print("\n--- REQUEST BODY ---")
        if rb is None:
            print(f"    (none or non-json: {type(e.get('request_body')).__name__})")
        else:
            walk(rb, a.show_values)
        print("\n--- RESPONSE BODY ---")
        sb = _maybe_json(e.get("response_body"))
        if sb is None:
            print(f"    (non-json, {len(e.get('response_body') or '')} chars)")
        else:
            walk(sb, a.show_values)
        return 0

    # summary table
    for e in job:
        url = e["url"].split("?", 1)[0]
        if a.api_only and "//api." not in url:
            continue
        q = e["url"].split("?", 1)[1] if "?" in e["url"] else ""
        qkeys = sorted({p.split("=")[0] for p in q.split("&") if p}) if q else []
        rb = _maybe_json(e.get("request_body"))
        sb = _maybe_json(e.get("response_body"))
        rk = sorted(rb.keys())[:12] if isinstance(rb, dict) else ("[list]" if isinstance(rb, list) else "-")
        sk = sorted(sb.keys())[:12] if isinstance(sb, dict) else ("[list]" if isinstance(sb, list) else "-")
        print(f"[{e['seq']:2d}] t+{str(e.get('ts_rel')):>7s} {e['method']:4s} {url}")
        if qkeys:
            print(f"      query keys: {qkeys}")
        print(f"      req {rk}")
        print(f"      -> {e.get('status')}  resp {sk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
