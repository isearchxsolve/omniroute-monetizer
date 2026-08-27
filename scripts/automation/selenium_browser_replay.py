#!/usr/bin/env python3
"""selenium_browser_replay.py — Replay captured sessions via Selenium attached to live Chrome.

Attaches to the operator's already-running, already-signed-in Chrome on :9222 using
Selenium's debuggerAddress. Re-fires each recorded HTTP exchange as a native fetch()
inside the matching origin tab — leveraging Chrome's genuine network stack, TLS,
HTTP/2, and cookie jar. No clicking, no typing, no sign-up. Replay only.
"""
from __future__ import annotations

import argparse, json, pathlib, re, sys, time, urllib.parse, uuid
from typing import Any, Dict, List, Optional, Tuple

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECRETS = ROOT / "state" / "secrets"
OUT = ROOT / "state" / "selenium_browser_replay.json"
sys.path.insert(0, str(HERE))

from universal_replay import UniversalSessionClient
from replay_check import classify, keyword_in_body

FETCH_TIMEOUT_MS = 90_000
MAX_BODY_CHARS = 4_000_000

_FORBIDDEN_EXACT = {
    "accept-charset", "accept-encoding", "access-control-request-headers",
    "access-control-request-method", "connection", "content-length", "cookie",
    "cookie2", "date", "dnt", "expect", "feature-policy", "host", "keep-alive",
    "origin", "referer", "te", "trailer", "transfer-encoding", "upgrade", "via",
}


def settable_headers(headers: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in (headers or {}).items():
        lk = k.lower()
        if lk in _FORBIDDEN_EXACT or lk.startswith("sec-") or lk.startswith("proxy-"):
            continue
        out[k] = v
    return out


def origin_of(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


# The recorded exchange often targets an API origin (api.1min.ai) while the live signed-in tab
# sits on the web-app origin (app.1min.ai). The browser itself sends these requests FROM the
# app tab — that is what "acting like a browser" means here. Map recorded API origin -> the
# origin of the live tab the request must be fired from.
API_ORIGIN_TO_TAB_ORIGIN = {
    "https://api.1min.ai": "https://app.1min.ai",
    "https://api.cohere.com": "https://dashboard.cohere.com",
    "https://api.groq.com": "https://console.groq.com",
    "https://api.monica.im": "https://monica.im",
    "https://api.cr-proxy.com": "https://you.com",
    "https://chat-api-v3.innerai.com": "https://app.innerai.com",
}


def registrable(host: str) -> str:
    parts = (host or "").lstrip(".").lower().split(":")[0].split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# Async fetch executed via execute_async_script. Callback receives the result object.
FETCH_JS = r"""
const cb = arguments[arguments.length - 1];
const ctrl = new AbortController();
const t0 = Date.now();
const timer = setTimeout(() => ctrl.abort(), __TIMEOUT__);
(async () => {
  try {
    const r = await fetch(__URL__, {
      method: __METHOD__,
      headers: __HEADERS__,
      body: __BODY__,
      credentials: 'include',
      redirect: 'follow',
      signal: ctrl.signal,
    });
    const hdrs = {};
    try { r.headers.forEach((v, k) => { hdrs[k] = v; }); } catch (e) {}
    let text = '';
    const dec = new TextDecoder();
    const reader = r.body.getReader();
    while (true) {
      const step = await reader.read();
      if (step.done) break;
      text += dec.decode(step.value, { stream: true });
      if (text.length > __MAXCHARS__) break;
      if (Date.now() - t0 > __TIMEOUT__) break;
      if (__EXPECT__ && text.toLowerCase().includes(__EXPECT__)) break;
    }
    try { reader.cancel(); } catch (e) {}
    clearTimeout(timer);
    cb({ ok: true, status: r.status, finalUrl: r.url, headers: hdrs,
         body: text, ms: Date.now() - t0 });
  } catch (e) {
    clearTimeout(timer);
    cb({ ok: false, error: String(e && e.name ? e.name + ': ' + e.message : e),
         ms: Date.now() - t0 });
  }
})();
"""


def build_fetch_js(url: str, method: str, headers: Dict[str, str],
                   body: Optional[str], expect: str) -> str:
    js = FETCH_JS
    js = js.replace("__TIMEOUT__", str(FETCH_TIMEOUT_MS))
    js = js.replace("__MAXCHARS__", str(MAX_BODY_CHARS))
    js = js.replace("__URL__", json.dumps(url))
    js = js.replace("__METHOD__", json.dumps(method.upper()))
    js = js.replace("__HEADERS__", json.dumps(settable_headers(headers)))
    js = js.replace("__BODY__", json.dumps(body) if body else "null")
    js = js.replace("__EXPECT__", json.dumps(expect.lower()) if expect else "null")
    return js


def inject_prompt_extended(client: UniversalSessionClient, prompt: str) -> str:
    if not client.base_body:
        return ""
    body = client.base_body
    injected = client._inject_prompt(prompt)
    if prompt in injected or json.dumps(prompt)[1:-1] in injected:
        return injected
    esc = json.dumps(prompt)[1:-1]
    extended_phrases = [
        "Omni sentinel shot: a lone lighthouse beam sweeping across dark ocean waves at midnight",
        "Omni sentinel shot", "Omni.", "Omni",
    ]
    for ph in extended_phrases:
        if ph in body:
            return body.replace(ph, esc if ('{"' in body or body.startswith("{")) else prompt)
        ph_url = urllib.parse.quote_plus(ph)
        if ph_url in body:
            return body.replace(ph_url, urllib.parse.quote_plus(esc))
    return injected


# ---------------------------------------------------------------------------
# CHROME GAP DOCTRINE — send-time reconstruction.
# Chrome's app does NOT resend recorded bytes. On every send it regenerates a
# set of per-request fields (fresh UUIDs, fresh timestamps, fresh nonces, fresh
# bearer pulled from localStorage). Replaying the recorded values is exactly why
# these hosts looked "dead". Reconstruct them here. Each rule: host substring ->
# list of (where, regex, generator). where in {"body","header:<name>"}.
# ---------------------------------------------------------------------------
def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _uuid4() -> str:
    return str(uuid.uuid4())


SEND_TIME_RULES: List[Tuple[str, List[Tuple[str, str, Any]]]] = [
    # mistral: messageId must be fresh or the server 409 "already".
    ("mistral", [("body", r'"messageId"\s*:\s*"[0-9a-f-]{36}"', lambda m: '"messageId":"' + _uuid4() + '"')]),
    # chathub: fresh streamId + fresh x-client-time (epoch ms).
    ("chathub", [
        ("body", r'"streamId"\s*:\s*"[0-9a-f-]{36}"', lambda m: '"streamId":"' + _uuid4() + '"'),
        ("header:x-client-time", r".*", lambda m: _now_ms()),
    ]),
    # felo: fresh search_uuid per question.
    ("felo", [("body", r'"search_uuid"\s*:\s*"[^"]+"', lambda m: '"search_uuid":"' + _uuid4()[:21] + '"')]),
    # huggingface: fresh generationId per message.
    ("huggingface", [("body", r'"generationId"\s*:\s*"[0-9a-f-]{36}"', lambda m: '"generationId":"' + _uuid4() + '"')]),
    # chatglm: fresh nonce/timestamp/request-id (x-sign needs the signing algo — deeper gap).
    ("chatglm", [
        ("header:x-nonce", r".*", lambda m: _uuid4().replace("-", "")[:16]),
        ("header:x-timestamp", r".*", lambda m: str(int(time.time()))),
        ("header:x-request-id", r".*", lambda m: _uuid4()),
    ]),
    # innerai: fresh device-id is fine; the gap is CORS origin mapping (handled separately).
]


def reconstruct_send_time(host: str, headers: Dict[str, str], body: Optional[str]) -> Tuple[Dict[str, str], Optional[str]]:
    """Apply per-host send-time field reconstruction. Returns (headers, body)."""
    headers = dict(headers or {})
    for sub, rules in SEND_TIME_RULES:
        if sub not in (host or "").lower():
            continue
        for where, pat, gen in rules:
            if where == "body" and body:
                body = re.sub(pat, gen, body, flags=re.I)
            elif where.startswith("header:"):
                hname = where.split(":", 1)[1]
                for k in list(headers.keys()):
                    if k.lower() == hname.lower():
                        headers[k] = re.sub(pat, gen, str(headers[k]), flags=re.I)
    return headers, body


# CHROME GAP DOCTRINE (auth side): some providers mint SHORT-LIVED bearer tokens that
# Chrome's app refreshes from browser storage at send-time. The recorded bearer is stale
# and the server rejects it ("invalid or expired jwt"). The fix is NOT a dead site — it is
# to harvest the LIVE token from the signed-in tab's storage and swap it into the header,
# exactly as Chrome's app does. Each entry: host-substring -> (js returning token or null,
# header name to overwrite). The JS runs in the resolved tab BEFORE the fetch.
LIVE_BEARER_RULES: Dict[str, Tuple[str, str]] = {
    # groq: Stytch-minted JWT. Live copy sits in the stytch_session_jwt cookie (and the
    # Stytch SDK state blob in localStorage). Verified 2026-08-27: harvesting it turns a
    # 401 "invalid or expired jwt" into HTTP 200 REPLAY_OK.
    "groq": (
        r"""
        (function(){
          try {
            var m = document.cookie.match(/(?:^|;\s*)stytch_session_jwt=([^;]+)/);
            if (m && m[1]) return decodeURIComponent(m[1]);
          } catch (e) {}
          try {
            for (var i = 0; i < localStorage.length; i++) {
              var k = localStorage.key(i);
              if (k && k.indexOf('stytch_sdk_state') === 0 && k.indexOf('::') === -1) {
                var v = localStorage.getItem(k) || '';
                var jm = v.match(/"session_jwt"\s*:\s*"([^"]+)"/) || v.match(/"jwt"\s*:\s*"([^"]+)"/);
                if (jm && jm[1]) return jm[1];
              }
            }
          } catch (e) {}
          return null;
        })()
        """,
        "authorization",
    ),
}


def harvest_live_bearer(driver, host: str, headers: Dict[str, str]) -> Tuple[Dict[str, str], Optional[str]]:
    """If this host mints short-lived tokens, pull the live one from the tab's storage and
    overwrite the auth header. Returns (headers, source-or-None). Must be called while the
    driver is focused on the host's signed-in tab."""
    headers = dict(headers or {})
    for sub, (harvest_js, header_name) in LIVE_BEARER_RULES.items():
        if sub not in (host or "").lower():
            continue
        try:
            # NOTE: strip() is load-bearing. A newline between `return` and the IIFE
            # triggers JS automatic-semicolon-insertion (`return;` + dead IIFE).
            token = driver.execute_script("return " + harvest_js.strip())
        except Exception:
            token = None
        if token:
            headers[header_name] = "Bearer " + str(token)
            return headers, sub
        return headers, None
    return headers, None


# CHROME GAP DOCTRINE (verdict side): streaming APIs split the answer across many
# frames (tRPC patches, SSE deltas). The phrase is present but never contiguous in
# the raw body. Aggregate all JSON text-bearing string values in order, then check.
_TEXT_FIELD_RE = re.compile(r'"(?:text|value|content|message|delta|answer|reply)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.I)


def aggregated_text(body: str) -> str:
    parts = []
    for m in _TEXT_FIELD_RE.finditer(body or ""):
        try:
            parts.append(json.loads('"' + m.group(1) + '"'))
        except Exception:
            parts.append(m.group(1))
    return "".join(parts)


def replay_session(file_path: pathlib.Path, driver, handle_by_origin: Dict[str, str],
                   prompt: str, expect: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {"file": file_path.name}
    try:
        client = UniversalSessionClient(file_path)
    except Exception as e:
        row.update(host="?", verdict="BAD_FILE", detail=f"unreadable: {str(e)[:100]}", latencyMs=0)
        return row

    host = client.raw.get("host") or origin_of(client.url)
    origin = origin_of(client.url)
    row["host"] = host
    row["recordedUrl"] = str(client.url)[:120]
    row["runFromOrigin"] = origin

    try:
        new_body = inject_prompt_extended(client, prompt) if client.base_body else None
    except Exception as e:
        row.update(verdict="BAD_FILE", detail=str(e)[:140], latencyMs=0)
        return row

    # CHROME GAP DOCTRINE: Chrome regenerates per-request fields on every send.
    # Reconstruct them so we send what Chrome would send, not stale recorded bytes.
    new_headers, new_body = reconstruct_send_time(host, client.headers, new_body)
    row["sendTimeReconstructed"] = True

    # Resolve the tab to fire the fetch from: exact origin -> explicit API->app map ->
    # registrable-domain fallback (api.groq.com matches console.groq.com via "groq.com").
    handle = handle_by_origin.get(origin)
    run_origin = origin
    if handle is None and origin in API_ORIGIN_TO_TAB_ORIGIN:
        run_origin = API_ORIGIN_TO_TAB_ORIGIN[origin]
        handle = handle_by_origin.get(run_origin)
    if handle is None:
        reg = registrable(origin_of(origin))
        for o, h in handle_by_origin.items():
            if registrable(origin_of(o)) == reg:
                handle, run_origin = h, o
                break
    if handle is None:
        row.update(verdict="NO_TAB", detail=f"no live tab for origin {origin}", latencyMs=0)
        return row
    row["runFromOrigin"] = run_origin

    try:
        driver.switch_to.window(handle)
    except Exception as e:
        row.update(verdict="ERROR", detail=f"switch_to failed: {str(e)[:100]}", latencyMs=0)
        return row

    # CHROME GAP DOCTRINE (auth side): harvest a live short-lived bearer from the signed-in
    # tab's storage and swap it into the auth header, exactly as Chrome's app does at send-time.
    new_headers, bearer_src = harvest_live_bearer(driver, host, new_headers)
    if bearer_src:
        row["liveBearerHarvested"] = bearer_src

    started = time.perf_counter()
    try:
        js = build_fetch_js(client.url, client.method, new_headers, new_body, expect)
        res = driver.execute_async_script(js)
    except Exception as e:
        row.update(verdict="ERROR", detail=f"execute_async_script failed: {str(e)[:120]}",
                   latencyMs=round((time.perf_counter() - started) * 1000))
        return row

    # CORS fallback: a cross-origin fetch from the app tab is refused by the browser's
    # web-security layer even though Chrome itself can reach the API. Fire the SAME request
    # from a tab sitting on the request's own origin (same-origin => no preflight). This is
    # exactly how the raw-CDP tool got api.1min.ai to REPLAY_OK.
    if isinstance(res, dict) and not res.get("ok") and "Failed to fetch" in str(res.get("error", "")):
        row["corsFallback"] = True
        try:
            # Selenium's native new_window (WebDriver protocol) is NOT popup-blocked, unlike
            # window.open. Open a tab on the request's own origin so the fetch is same-origin.
            driver.switch_to.new_window("tab")
            fresh_handle = driver.current_window_handle
            driver.get(origin + "/")
            time.sleep(3.0)
            row["corsFallbackOrigin"] = driver.current_url[:60]
            res = driver.execute_async_script(js)
            driver.close()
            driver.switch_to.window(handle)
        except Exception as e:
            row["corsFallbackError"] = str(e)[:120]
            try:
                driver.switch_to.window(handle)
            except Exception:
                pass

    row["latencyMs"] = round((time.perf_counter() - started) * 1000)

    if not isinstance(res, dict):
        row.update(verdict="ERROR", detail="No result from fetch")
        return row
    if not res.get("ok"):
        row.update(verdict="ERROR", detail=f"fetch error: {str(res.get('error'))[:140]}")
        return row

    status = res.get("status")
    body = res.get("body") or ""
    row["status"] = status
    row["bodyBytes"] = len(body)
    row["contentType"] = (res.get("headers") or {}).get("content-type", "")[:80]

    if keyword_in_body(body, expect):
        row["verdict"] = "REPLAY_OK"
        row["detail"] = f"Selenium in-browser fetch status {status}, phrase verified ({len(body)}B)"
    elif keyword_in_body(aggregated_text(body), expect):
        row["verdict"] = "REPLAY_OK"
        row["detail"] = (f"Selenium in-browser fetch status {status}, phrase verified via "
                         f"frame aggregation ({len(body)}B raw)")
    else:
        verdict, detail = classify(body, status, None, expect)
        row["verdict"] = verdict
        row["detail"] = detail
        # Doctrine evidence: keep a long preview so the send-time gap is visible.
        row["bodyPreview"] = body[:1600]
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--only", default="", help="comma-separated host/file substrings")
    ap.add_argument("--prompt", default="Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks")
    ap.add_argument("--expect", default="the holy cow jumps over the stricks")
    a = ap.parse_args()

    files = sorted(SECRETS.glob("session_*.json"))
    if a.only:
        want = [s.strip().lower() for s in a.only.split(",") if s.strip()]
        files = [f for f in files if any(w in f.name.lower() for w in want)]
    if not files:
        print(f"No session_*.json found in {SECRETS}")
        return 1

    print(f"Attaching Selenium to live Chrome on :{a.port} ...", flush=True)
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{a.port}")
    t0 = time.perf_counter()
    driver = webdriver.Chrome(options=opts)
    driver.set_script_timeout((FETCH_TIMEOUT_MS // 1000) + 15)
    print(f"Attached in {time.perf_counter()-t0:.1f}s. Windows: {len(driver.window_handles)}", flush=True)

    # Map origin -> window handle (first match wins).
    handle_by_origin: Dict[str, str] = {}
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            o = origin_of(driver.current_url)
            handle_by_origin.setdefault(o, h)
        except Exception:
            continue
    print(f"Mapped {len(handle_by_origin)} origins to tabs", flush=True)

    rows: list[Dict[str, Any]] = []
    for f in files:
        row = replay_session(f, driver, handle_by_origin, a.prompt, a.expect)
        rows.append(row)
        mark = "OK " if row["verdict"] == "REPLAY_OK" else "   "
        print(f"  {mark}{row['host'][:32]:32s} {row['verdict']:12s} "
              f"{row.get('latencyMs', 0):6d}ms  {row.get('detail', '')[:70]}", flush=True)

    ok = sorted({r["host"] for r in rows if r["verdict"] == "REPLAY_OK"})
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport": "Selenium debuggerAddress attached to live Chrome (real browser instance)",
        "question": "Does captured session replay when Selenium drives the real signed-in browser?",
        "results": rows,
        "summary": {"replayable": ok,
                    "other": sorted({r["host"] for r in rows if r["verdict"] != "REPLAY_OK"})}
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReplayable ({len(ok)}): {', '.join(ok) or 'none'}")
    print(f"Wrote report to {OUT}")
    # Do NOT driver.quit() — we attached to the operator's live Chrome.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
