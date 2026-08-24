"""grab_session.py — capture a soft-target chat provider's genuine browser SESSION, read-only.

The "omni way" for auth providers (per the operator): don't reconstruct an API request — that is
what trips the upstream personal_search gate ("Sign up and repeat your request."). Instead grab the
real logged-in session cookie and RECORD one genuine chat exchange over the wire, so it can later be
replayed byte-for-byte server-side. Replaying the genuine session shape is not gated, and it drops
the single-tab CDP serialization limit (many parallel server-side requests become possible).

Strictly READ-ONLY against the ROBOT Chrome (port 9222, the automation profile — never the
operator's live personal Chrome): it reads cookies and passively records network events. It never
sends a chat, never POSTs, never navigates, never mutates the account. Cookie VALUES, the exact
request headers, and the recorded exchange are written to a gitignored secret file under
state/secrets/. STDOUT shows METADATA ONLY (names, flags, lengths, payload shape) — never a secret
value, never the Cookie header, never a cookie's value.

    python grab_session.py cookie  [--match veoaifree.com/gemini] [--host veoaifree.com]
    python grab_session.py record  [--match ...] [--url-substr veo-proxy.php] [--wait 180]

The design is provider-agnostic on purpose: veoaifree is soft-target #1, but the same two verbs
(grab the cookie jar, record one exchange) generalize to LMArena and the hundreds of other free
chat surfaces the operator wants to harness. --host/--url-substr are the only per-provider knobs.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import time
from typing import Any, Dict, List, Optional

import websocket  # noqa: F401  (used indirectly via cdp.Page.ws)
from cdp import Page, DEFAULT_PORT

SECRETS = pathlib.Path(r"D:\omniroute-monetizer\state\secrets")

# Header names whose values are identity/secret material — persisted to the secret file, but only
# their PRESENCE (never the value) is ever printed. Everything else (model, ua, sec-ch-*) is safe.
_SENSITIVE_HDR = {"cookie", "authorization", "x-wp-nonce", "x-csrf-token", "set-cookie"}
# Payload fields that are identity/secret-shaped — redacted from STDOUT, kept in the secret file.
_SENSITIVE_FIELD = {"user_name", "frontend_uuid", "uuid", "email", "token", "nonce", "session"}


def _secret_path(host: str) -> pathlib.Path:
    slug = host.replace(".", "_").replace("/", "_")
    return SECRETS / f"session_{slug}.json"


def _write_secret(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def grab_cookie(match: str, host: str, port: int) -> int:
    """Read the logged-in cookie jar for `host` + the browser context needed to impersonate it.

    Uses Network.getCookies (a command, not an event) so we never enable the event stream and never
    flood the socket. getCookies with an explicit url returns HttpOnly cookies too (which is exactly
    what document.cookie in-page CANNOT see — the WordPress login cookie lives there)."""
    with Page(match, port=port, timeout=30) as p:
        url = f"https://{host}/"
        res = p.send("Network.getCookies", {"urls": [url]}, timeout=20)
        cookies: List[Dict[str, Any]] = res.get("cookies", []) or []
        # Non-secret browser context for faithful replay ("pretending to actual browser session").
        # BEST-EFFORT: heavy SPAs (most video providers) can be slow to answer Runtime.evaluate —
        # the COOKIE JAR is the payload, so a slow/failed probe must NEVER discard a good grab.
        # veoaifree exposes login state on window.VEO_CHAT_CONFIG; other providers just return the
        # generic navigator/location fields, and we fall back to a jar-shape auth heuristic below.
        try:
            ctx = p.evaluate(
                "({ua: navigator.userAgent, origin: location.origin, href: location.href,"
                " proxyUrl: (window.VEO_CHAT_CONFIG||{}).proxyUrl || null,"
                " userName: (window.VEO_CHAT_CONFIG||{}).currentUserName || null,"
                " loggedIn: !!(window.VEO_CHAT_CONFIG||{}).isLoggedIn })",
                timeout=8,
            ) or {}
        except Exception as e:
            ctx = {"probe_error": str(e)[:80]}

    if not cookies:
        print(f"!! no cookies returned for {host} — is the tab logged in? (match={match!r})")
        return 1

    cookie_header = "; ".join(f'{c.get("name")}={c.get("value","")}' for c in cookies)
    # Generic auth signal (works past veoaifree): a persistent, httpOnly, non-trivial cookie is the
    # shape of a real session token. Not proof, but a good triage flag for which grabs to record next.
    likely_authed = any(
        c.get("httpOnly") and isinstance(c.get("expires"), (int, float))
        and c.get("expires", -1) > 0 and len(c.get("value", "") or "") >= 20
        for c in cookies
    )
    secret = {
        "host": host,
        "captured_at": int(time.time()),
        "match": match,
        "context": ctx,                       # ua/origin/href/proxyUrl/userName (userName is PII)
        "likely_authed": likely_authed,       # jar-shape heuristic; veoaifree loggedIn is authoritative
        "cookie_header": cookie_header,        # ready to send as the Cookie: request header
        "cookies": cookies,                    # full jar incl. values (gitignored file only)
    }
    path = _secret_path(host)
    _write_secret(path, secret)

    # ---- STDOUT: metadata only, never a value ----
    print(f"=== session grabbed: {host} ===  (secret -> {path})")
    print(f"  likely_authed: {likely_authed}   veo_loggedIn: {ctx.get('loggedIn')}"
          f"   proxyUrl set: {bool(ctx.get('proxyUrl'))}   userName set: {bool(ctx.get('userName'))}"
          f"   probe: {'ok' if 'probe_error' not in ctx else 'slow/failed'}")
    print(f"  {len(cookies)} cookies:")
    for c in cookies:
        val_len = len(c.get("value", "") or "")
        exp = c.get("expires", -1)
        persistent = isinstance(exp, (int, float)) and exp > 0
        print(f"    - {c.get('name'):32s} dom={str(c.get('domain','')):22s} "
              f"path={str(c.get('path','/')):10s} httpOnly={str(bool(c.get('httpOnly'))):5s} "
              f"secure={str(bool(c.get('secure'))):5s} sameSite={str(c.get('sameSite','-')):6s} "
              f"persistent={str(persistent):5s} len={val_len}")
    print(f"  cookie_header len={len(cookie_header)} (value withheld)")
    return 0


def _session_cookie(cookies: List[Dict[str, Any]], prefix: str) -> Optional[Dict[str, Any]]:
    """Pick the auth cookie: first by name-prefix, else the httpOnly+persistent one with the
    longest value (a good dirty-and-easy heuristic that generalizes past WordPress)."""
    for c in cookies:
        if (c.get("name") or "").startswith(prefix):
            return c
    cands = [c for c in cookies if c.get("httpOnly")
             and isinstance(c.get("expires"), (int, float)) and c.get("expires", -1) > 0]
    return max(cands, key=lambda c: len(c.get("value", "") or ""), default=None)


def _runway_days(cookie: Optional[Dict[str, Any]], now: float) -> Optional[float]:
    if not cookie:
        return None
    exp = cookie.get("expires", -1)
    if not isinstance(exp, (int, float)) or exp <= 0:
        return None            # session cookie (dies on browser close) — no fixed runway
    return round((exp - now) / 86400.0, 2)


def keepalive(match: str, host: str, prefix: str, interval: int, once: bool, port: int,
              touch_url: Optional[str], warn_days: float = 2.0) -> int:
    """Keep the logged-in session warm and — unlike omni — never let a dead session look alive.

    Each cycle: (1) touch a benign authenticated GET in-page (may slide the cookie's expiry on WP
    setups that refresh on activity), (2) re-grab the jar so our stored cookie is always the fresh
    one, (3) verify REAL liveness (server-rendered isLoggedIn flag + session cookie present + expiry
    runway > 0), not mere cookie presence. Writes an honest status block to the secret file and
    prints metadata only (alive, runway in days, whether the cookie refreshed this cycle)."""
    path = _secret_path(host)
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    prev_sc = _session_cookie(prev.get("cookies", []) or [], prefix)
    prev_val = (prev_sc or {}).get("value")

    def cycle() -> Dict[str, Any]:
        nonlocal prev_val
        with Page(match, port=port, timeout=30) as p:
            turl = touch_url or f"https://{host}/"
            # read-only authenticated GET, in-page so the cookie never leaves the browser to touch
            touch = p.evaluate(
                "(async()=>{try{const r=await fetch(" + json.dumps(turl) +
                ",{credentials:'include',cache:'no-store'});"
                "return {ok:r.ok,status:r.status};}catch(e){return {ok:false,err:String(e)};}})()",
                timeout=45) or {}
            ctx = p.evaluate(
                "({loggedIn: !!(window.VEO_CHAT_CONFIG||{}).isLoggedIn,"
                " userName: (window.VEO_CHAT_CONFIG||{}).currentUserName || null,"
                " ua: navigator.userAgent, origin: location.origin, href: location.href,"
                " proxyUrl: (window.VEO_CHAT_CONFIG||{}).proxyUrl || null})", timeout=15) or {}
            jar = p.send("Network.getCookies", {"urls": [f"https://{host}/"]},
                         timeout=20).get("cookies", []) or []
        now = time.time()
        sc = _session_cookie(jar, prefix)
        runway = _runway_days(sc, now)
        refreshed = bool(sc and prev_val and sc.get("value") != prev_val)
        alive = bool(ctx.get("loggedIn") and sc and (runway is None or runway > 0))
        reason = ("ok" if alive else
                  "NOT_LOGGED_IN" if not ctx.get("loggedIn") else
                  "NO_SESSION_COOKIE" if not sc else "EXPIRED")
        secret = {
            "host": host, "match": match, "captured_at": int(now),
            "context": ctx,
            "cookie_header": "; ".join(f'{c.get("name")}={c.get("value","")}' for c in jar),
            "cookies": jar,
            "session_cookie_name": (sc or {}).get("name"),
            "status": {"alive": alive, "reason": reason, "runway_days": runway,
                       "refreshed": refreshed, "touch": touch, "checked_at": int(now)},
        }
        _write_secret(path, secret)
        if sc:
            prev_val = sc.get("value")
        return secret["status"]

    while True:
        st = cycle()
        flag = "ALIVE" if st["alive"] else "DEAD "
        rw = "session-only" if st["runway_days"] is None else f"{st['runway_days']}d"
        print(f"[{flag}] {host}  reason={st['reason']}  runway={rw}  "
              f"refreshed={st['refreshed']}  touch={st['touch'].get('status', st['touch'])}")
        if not st["alive"]:
            print(f"  !! session for {host} is NOT usable ({st['reason']}). A login wall is a "
                  f"correct outcome to report — re-login in the browser; do NOT auto-work-around.")
        elif st["runway_days"] is not None and st["runway_days"] < warn_days:
            print(f"  ~~ WARN: {host} session runway < {warn_days}d ({st['runway_days']}d left). "
                  f"Re-login in the browser to reset the ~14-day cookie before it lapses.")
        if once:
            return 0 if st["alive"] else 2
        time.sleep(max(60, interval))


def record_exchange(match: str, host: str, url_substr: str, wait: int, port: int) -> int:
    """Passively record ONE genuine chat/generate exchange (the operator sends it) as replay ground
    truth. Read-only: we only turn on the CDP Network event stream and watch — never send anything.
    Captures request method/url/headers/body + response status/headers/body for the first request
    whose URL contains `url_substr`, and stores the exact wire shape in the secret file."""
    print(f"[record] armed on {host} — watching for a request containing {url_substr!r}.")
    print(f"[record] >>> now SEND ONE MESSAGE in the {host} chat tab (or trigger one video). "
          f"Waiting up to {wait}s...")
    reqs: Dict[str, Dict[str, Any]] = {}
    extra: Dict[str, Dict[str, Any]] = {}
    resp: Dict[str, Dict[str, Any]] = {}
    seen: Optional[str] = None
    finished = False
    deadline = time.time() + wait
    with Page(match, port=port, timeout=wait + 30) as p:
        p.send("Network.enable", timeout=20)
        while time.time() < deadline and not finished:
            p.ws.settimeout(2.0)
            try:
                msg = json.loads(p.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                continue
            meth, pr = msg.get("method"), msg.get("params", {})
            if meth == "Network.requestWillBeSent":
                r = pr.get("request", {})
                if url_substr in (r.get("url") or ""):
                    rid = pr.get("requestId")
                    reqs[rid] = {"url": r.get("url"), "method": r.get("method"),
                                 "headers": r.get("headers", {}),
                                 "postData": r.get("postData"), "hasPostData": r.get("hasPostData")}
                    if seen is None:
                        seen = rid
                        print(f"[record] captured the REQUEST ({r.get('method')} {url_substr}); "
                              f"waiting for the response stream to finish...", flush=True)
            elif meth == "Network.requestWillBeSentExtraInfo":
                rid = pr.get("requestId")
                if rid in reqs:
                    extra[rid] = pr.get("headers", {})            # actual sent headers incl. Cookie
            elif meth == "Network.responseReceived":
                rid = pr.get("requestId")
                if rid in reqs:
                    rr = pr.get("response", {})
                    resp[rid] = {"status": rr.get("status"), "headers": rr.get("headers", {}),
                                 "mimeType": rr.get("mimeType")}
            elif meth == "Network.loadingFinished":
                if pr.get("requestId") == seen and seen is not None:
                    finished = True                                # captured a full exchange
        if seen is None:
            print(f"[record] no {url_substr!r} request seen within {wait}s — nothing captured "
                  f"(am I on the right tab? --match).")
            return 1
        target = seen
        body, b64 = "", False
        if finished:
            try:
                b = p.send("Network.getResponseBody", {"requestId": target}, timeout=30)
                body, b64 = b.get("body", ""), bool(b.get("base64Encoded"))
            except Exception as e:  # SSE bodies occasionally aren't retained; keep the rest
                body = f"<no body: {e}>"
        else:
            body = "<response still streaming at deadline; request template captured>"
        post = reqs[target].get("postData")
        if not post and reqs[target].get("hasPostData"):
            try:
                post = p.send("Network.getRequestPostData", {"requestId": target},
                              timeout=20).get("postData")
            except Exception:
                post = None

    rec = {
        "url": reqs[target]["url"], "method": reqs[target]["method"],
        "request_headers": {**reqs[target].get("headers", {}), **extra.get(target, {})},
        "request_body": post,
        "response": resp.get(target, {}),
        "response_body": body, "response_base64": b64,
        "finished": finished,
        "recorded_at": int(time.time()),
    }
    path = _secret_path(host)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"host": host}
    data["recorded_exchange"] = rec
    _write_secret(path, data)

    # ---- STDOUT: scrubbed summary only ----
    hdr_names = sorted(rec["request_headers"].keys())
    safe_names = [h for h in hdr_names if h.lower() not in _SENSITIVE_HDR]
    sens_present = [h for h in hdr_names if h.lower() in _SENSITIVE_HDR]
    print(f"[record] captured {rec['method']} {url_substr}  -> HTTP {rec['response'].get('status')}"
          f"  mime={rec['response'].get('mimeType')}  stream_finished={finished}")
    print(f"  request headers: {len(hdr_names)} ({', '.join(safe_names[:12])}"
          f"{' …' if len(safe_names) > 12 else ''}); sensitive present (withheld): {sens_present}")
    try:
        payload = json.loads(post) if post else {}
        shape = {k: (f"<{_SENSITIVE_FIELD and 'redacted'}>" if k.lower() in _SENSITIVE_FIELD
                     else (f"str[{len(v)}]" if isinstance(v, str)
                           else (f"list[{len(v)}]" if isinstance(v, list) else v)))
                 for k, v in payload.items()}
        print(f"  request payload shape: {json.dumps(shape, ensure_ascii=False)}")
    except Exception:
        print(f"  request body: {'present' if post else 'none'} (not JSON)")
    rb = body if isinstance(body, str) else ""
    gated = "Sign up and repeat" in rb
    print(f"  response body: {len(rb)} bytes  sse={'event:' in rb or 'data:' in rb}  gated={gated}")
    print(f"  full exchange -> {path}  (secret; gitignored)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--match", default="veoaifree.com/gemini",
                    help="substring of the logged-in tab url/title")
    ap.add_argument("--host", default="veoaifree.com", help="cookie host to grab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cookie", help="grab the cookie jar + browser context now (no chat needed)")
    r = sub.add_parser("record", help="passively record ONE genuine chat exchange (user sends it)")
    r.add_argument("--url-substr", default="veo-proxy.php",
                   help="only capture requests whose URL contains this")
    r.add_argument("--wait", type=int, default=180, help="seconds to wait for the exchange")
    k = sub.add_parser("keepalive", help="keep the session warm + verify real liveness (never a corpse)")
    k.add_argument("--session-prefix", default="wordpress_logged_in_",
                   help="name prefix of the auth cookie (WP default; override per provider)")
    k.add_argument("--interval", type=int, default=3600, help="seconds between cycles")
    k.add_argument("--touch-url", default=None, help="benign authed GET to keep warm (default: host root)")
    k.add_argument("--warn-days", type=float, default=2.0, help="warn while alive if runway drops below this")
    k.add_argument("--once", action="store_true", help="run a single cycle and exit (for cron/probe)")

    a = ap.parse_args()
    if a.cmd == "cookie":
        return grab_cookie(a.match, a.host, a.port)
    if a.cmd == "record":
        return record_exchange(a.match, a.host, a.url_substr, a.wait, a.port)
    if a.cmd == "keepalive":
        return keepalive(a.match, a.host, a.session_prefix, a.interval, a.once, a.port,
                         a.touch_url, a.warn_days)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
