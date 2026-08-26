"""record_video_job.py — record the FULL async API call sequence of ONE genuine video generation.

veoaifree chat is synchronous (one SSE request), so grab_session.py's single-shot `record` captures
it in one go. Video providers are ASYNC: submit -> poll job status -> fetch result URL, spread across
many requests. This records the WHOLE first-party API conversation during one operator-triggered
generation, so the replay adapter can be reverse-engineered offline from the captured shape.

STRICTLY READ-ONLY / PASSIVE against the ROBOT Chrome (port 9222 automation profile — never the
operator's live Chrome). It only turns on the CDP Network event stream and watches: it never sends a
request, never navigates, never mutates the account. The operator triggers exactly one generation in
the tab. The full wire (headers incl. Cookie, request/response bodies) is written to the gitignored
secret file; STDOUT shows METADATA ONLY (method, host+path with the query STRIPPED, status, sizes,
payload key-shape, flags) — never a value, never a query string, never a cookie/token.

    python record_video_job.py --match app.heygen.com --host app.heygen.com --wait 420
      optional: --api-substr heygen   (default = the site's second-level domain label)
                --keep-all            (also record non-first-party XHR/Fetch; off by default)
"""
from __future__ import annotations
import argparse
import json
import pathlib
import time
from typing import Any, Dict, List

import websocket  # noqa: F401  (used indirectly via cdp.Page.ws)
from cdp import Page, DEFAULT_PORT

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")
_SENSITIVE_HDR = {"cookie", "authorization", "x-wp-nonce", "x-csrf-token", "set-cookie",
                  "x-api-key", "x-auth-token", "x-session-token", "token"}
# analytics/telemetry hosts we never bother recording (noise, and sometimes third-party PII)
_TRACKERS = ("google-analytics", "googletagmanager", "doubleclick", "gstatic", "google.com/ads",
             "segment.", "segment.io", "intercom", "sentry", "amplitude", "mixpanel", "hotjar",
             "clarity.ms", "fullstory", "datadoghq", "posthog", "cloudflareinsights", "facebook",
             "tiktok", "bytedance", "analytics", "/collect", "beacon", "recaptcha")
_BODY_CAP = 20000  # chars kept per response body in the secret file (job JSON is small)
_PAYWALL = ("insufficient", "upgrade your plan", "not enough credit", "payment required",
            "subscribe", "quota exceeded", "purchase", "out of credit", "no credit", "upgrade to")


def _secret_path(host: str) -> pathlib.Path:
    return SECRETS / f"session_{host.replace('.', '_').replace('/', '_')}.json"


def _sld(host: str) -> str:
    parts = [p for p in host.split(".") if p]
    return parts[-2] if len(parts) >= 2 else host


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def _is_tracker(url: str) -> bool:
    u = url.lower()
    return any(t in u for t in _TRACKERS)


def record_job(match: str, host: str, api_substr: str, wait: int, port: int, keep_all: bool) -> int:
    print(f"[record-job] armed on {host} — capturing first-party API calls containing {api_substr!r}"
          f"{' (+ all XHR/Fetch)' if keep_all else ''}.")
    print(f"[record-job] >>> now trigger ONE video generation in the {host} tab. Watching {wait}s...")
    print(f"[record-job] (card/credit/plan wall => STOP, do not pay; a wall is a reportable outcome.)",
          flush=True)
    reqs: Dict[str, Dict[str, Any]] = {}
    extra: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    t_start = time.time()
    deadline = t_start + wait

    def want(url: str, rtype: str) -> bool:
        if _is_tracker(url) or rtype not in ("XHR", "Fetch"):
            return False
        return True if keep_all else (api_substr in url.lower())

    with Page(match, port=port, timeout=wait + 30) as p:
        p.send("Network.enable", timeout=20)
        last_activity = time.time()
        while time.time() < deadline:
            p.ws.settimeout(2.0)
            try:
                msg = json.loads(p.ws.recv())
            except websocket.WebSocketTimeoutException:
                # settle: once we've captured something, stop if 30s pass with no new first-party call
                if order and time.time() - last_activity > 30:
                    break
                continue
            except Exception:
                continue
            meth, pr = msg.get("method"), msg.get("params", {})
            if meth == "Network.requestWillBeSent":
                r = pr.get("request", {}) or {}
                url, rtype = r.get("url") or "", pr.get("type") or ""
                if not want(url, rtype):
                    continue
                rid = pr.get("requestId")
                reqs[rid] = {"seq": len(order), "url": url, "method": r.get("method"),
                             "type": rtype, "headers": r.get("headers", {}),
                             "postData": r.get("postData"), "hasPostData": r.get("hasPostData"),
                             "ts_rel": round(time.time() - t_start, 2)}
                order.append(rid)
                last_activity = time.time()
                print(f"  [{reqs[rid]['seq']:2d}] {str(r.get('method')):4s} "
                      f"{_strip_query(url)[:80]}", flush=True)
            elif meth == "Network.requestWillBeSentExtraInfo":
                rid = pr.get("requestId")
                if rid in reqs:
                    extra[rid] = pr.get("headers", {})              # actual sent headers incl. Cookie
            elif meth == "Network.responseReceived":
                rid = pr.get("requestId")
                if rid in reqs:
                    rr = pr.get("response", {}) or {}
                    reqs[rid]["status"] = rr.get("status")
                    reqs[rid]["resp_headers"] = rr.get("headers", {})
                    reqs[rid]["mimeType"] = rr.get("mimeType")
                    last_activity = time.time()
            elif meth == "Network.loadingFinished":
                rid = pr.get("requestId")
                if rid in reqs and "body" not in reqs[rid]:
                    try:
                        b = p.send("Network.getResponseBody", {"requestId": rid}, timeout=20)
                        body = b.get("body", "") or ""
                        reqs[rid]["response_base64"] = bool(b.get("base64Encoded"))
                        reqs[rid]["body"] = body[:_BODY_CAP]
                        reqs[rid]["body_truncated"] = len(body) > _BODY_CAP
                    except Exception as e:
                        reqs[rid]["body"] = f"<no body: {e}>"
                    if not reqs[rid].get("postData") and reqs[rid].get("hasPostData"):
                        try:
                            reqs[rid]["postData"] = p.send("Network.getRequestPostData",
                                                           {"requestId": rid},
                                                           timeout=15).get("postData")
                        except Exception:
                            pass
                    last_activity = time.time()

    if not order:
        print(f"[record-job] no first-party API calls containing {api_substr!r} seen in {wait}s — "
              f"did a generation actually start on the {host} tab? (check --match / --api-substr)")
        return 1

    job = []
    for rid in order:
        e = reqs[rid]
        job.append({
            "seq": e["seq"], "ts_rel": e.get("ts_rel"), "method": e.get("method"),
            "url": e.get("url"), "type": e.get("type"),
            "request_headers": {**e.get("headers", {}), **extra.get(rid, {})},
            "request_body": e.get("postData"),
            "status": e.get("status"), "mimeType": e.get("mimeType"),
            "response_headers": e.get("resp_headers", {}),
            "response_body": e.get("body"), "response_base64": e.get("response_base64", False),
            "body_truncated": e.get("body_truncated", False),
        })

    path = _secret_path(host)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"host": host}
    data["recorded_job"] = {"recorded_at": int(time.time()), "api_substr": api_substr,
                            "exchanges": job}
    # Stamp the modality the recorder just proved. Without it session_pool defaulted the seat to
    # "chat", so pool.live(modality="video") never saw it and the :8189 face reported no capacity.
    # setdefault, not assignment: a host that serves BOTH (veoaifree) keeps its declared modality
    # rather than having its chat dispatch silently converted to video.
    data.setdefault("modality", "video")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- STDOUT: metadata only ----
    print(f"\n[record-job] captured {len(job)} first-party exchange(s) -> {path} (secret; gitignored)\n")
    paywall_hit = False
    for e in job:
        rb = e["response_body"] if isinstance(e["response_body"], str) else ""
        gated = any(w in rb.lower() for w in _PAYWALL) or e.get("status") == 402
        paywall_hit = paywall_hit or gated
        post_shape = "-"
        if e["request_body"]:
            try:
                post_shape = "{" + ",".join(sorted(json.loads(e["request_body"]).keys())[:10]) + "}"
            except Exception:
                post_shape = f"raw[{len(e['request_body'])}]"
        print(f"  [{e['seq']:2d}] {str(e['method']):4s} {_strip_query(e['url'])[:70]}")
        print(f"        -> {e.get('status')} {e.get('mimeType')}  req={post_shape}  "
              f"resp={len(rb)}b{'  <<PAYWALL?' if gated else ''}")
    sens = sorted({h for e in job for h in e["request_headers"] if h.lower() in _SENSITIVE_HDR})
    print(f"\n  auth headers present (withheld): {sens}")
    if paywall_hit:
        print("\n  !! PAYWALL/CREDIT language in a response. If generation was blocked, this provider "
              "is walled for this account — report it; do NOT pay or work around.")
    print("\n  Next: inspect the secret offline to identify submit -> poll -> result, then write the "
          "adapter. (Bodies live in the gitignored secret, not printed here.)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--match", required=True, help="substring of the provider tab url/title")
    ap.add_argument("--host", required=True, help="cookie host / secret file key")
    ap.add_argument("--api-substr", default=None,
                    help="only record URLs containing this (default: the host's SLD label)")
    ap.add_argument("--wait", type=int, default=300, help="seconds to watch for the generation")
    ap.add_argument("--keep-all", action="store_true", help="also record non-first-party XHR/Fetch")
    a = ap.parse_args()
    return record_job(a.match, a.host, (a.api_substr or _sld(a.host)).lower(),
                      a.wait, a.port, a.keep_all)


if __name__ == "__main__":
    raise SystemExit(main())
