#!/usr/bin/env python3
"""browser_replay.py — replay captured sessions from INSIDE the real browser.

No impersonation. curl_cffi mimics a browser fingerprint; this tool does not
mimic anything — the replay is executed as a fetch() inside the live Chrome tab
on seat1 (CDP :9222), so the request travels through Chrome's genuine network
stack: real TLS/JA3, real HTTP/2 settings, real cookie jar, and the browser
natively fills its own protocol headers (sec-ch-ua, sec-fetch-*, Referer,
Origin, Host, Content-Length). The gap between "impersonator" and "browser"
does not exist here, because the client IS the browser.

Why fetch() and not re-typing headers: the Fetch API forbids JS from setting
the browser's own protocol headers (Cookie, sec-*, Origin, Referer, Host,
Content-Length, ...) — which is exactly what we want. Those are the headers a
mitm/impersonator gets wrong; here Chrome computes them itself from live state.

Law 4 holds: the recorded request is replayed with ONE sentinel substitution.
We strip only the headers fetch refuses to let JS set; the browser supplies
them natively. credentials:'include' sends the tab's real cookie jar.

Law 5 holds: walls/captchas in the response are reported, never hammered.

Usage:
    python scripts/automation/browser_replay.py [--only host1,host2] [--port 9222]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECRETS = ROOT / "state" / "secrets"
OUT = ROOT / "state" / "browser_replay.json"

sys.path.insert(0, str(HERE))

from capture_sessions_cdp import CDP, CDPError, targets          # noqa: E402
from universal_replay import UniversalSessionClient, ChatError    # noqa: E402
from replay_check import classify, keyword_in_body                # noqa: E402

FETCH_TIMEOUT_MS = 90_000
MAX_BODY_CHARS = 4_000_000

# Headers the Fetch API forbids JS to set. This is a feature, not a loss: for
# every one of these the browser computes the correct live value itself —
# Cookie from its real jar, sec-ch-ua/sec-fetch-* from its own identity,
# Referer/Origin from the tab, Host/Content-Length from the wire. An
# impersonator must forge these and forges them wrong; the browser just sends
# them. (https://fetch.spec.whatwg.org/#forbidden-header-name)
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


def list_pages(port: int) -> list[dict]:
    return [t for t in targets(port)]


def find_tab(pages: list[dict], origin: str) -> Optional[dict]:
    for t in pages:
        try:
            if origin_of(t.get("url", "")) == origin:
                return t
        except ValueError:
            continue
    return None


def create_tab(port: int, url: str) -> Optional[dict]:
    """Open a fresh tab at the given URL via the DevTools HTTP endpoint.

    /json/new requires PUT since Chrome 111."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe=':/?&=%')}",
                                 method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def close_tab(port: int, target_id: str) -> None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{target_id}", timeout=10):
            pass
    except Exception:
        pass


FETCH_JS = r"""
(async () => {
  const ctrl = new AbortController();
  const t0 = Date.now();
  const timer = setTimeout(() => ctrl.abort(), __TIMEOUT__);
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
    return { ok: true, status: r.status, finalUrl: r.url, headers: hdrs,
             body: text, ms: Date.now() - t0 };
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, error: String(e && e.name ? e.name + ': ' + e.message : e),
             ms: Date.now() - t0 };
  }
})()
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


class TabSession:
    """A CDP attachment to one tab, created on demand, closed if we made it."""

    def __init__(self, port: int, page: dict, created: bool):
        self.port = port
        self.page = page
        self.created = created
        self.cdp: Optional[CDP] = None

    def attach(self) -> CDP:
        if self.cdp is None:
            self.cdp = CDP(self.page["webSocketDebuggerUrl"], timeout=150.0)
        return self.cdp

    def evaluate(self, expr: str, timeout: float = 140.0) -> Any:
        return self.attach().call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
            timeout=timeout).get("result", {}).get("value")

    def close(self) -> None:
        if self.cdp is not None:
            self.cdp.close()
        if self.created:
            close_tab(self.port, self.page.get("id", ""))


def get_tab_session(port: int, pages: list[dict], origin: str) -> TabSession:
    """Prefer an existing tab on the recorded request's origin (the faithful
    same-origin context); otherwise open a fresh tab there so the fetch runs
    with that origin's real cookie jar."""
    tab = find_tab(pages, origin)
    if tab:
        return TabSession(port, tab, created=False)
    new = create_tab(port, origin + "/")
    if not new:
        raise RuntimeError(f"NO_TAB: no live tab on {origin} and could not open one")
    time.sleep(4.0)                       # let the page settle so fetch has an origin
    return TabSession(port, new, created=True)


def replay_one(path: pathlib.Path, port: int, pages: list[dict],
               prompt: str, expect: str,
               tab_cache: Dict[str, TabSession]) -> Dict[str, Any]:
    row: Dict[str, Any] = {"file": path.name}
    try:
        client = UniversalSessionClient(path)
    except Exception as e:
        row.update(host="?", verdict="BAD_FILE", detail=f"unreadable: {str(e)[:100]}", latencyMs=0)
        return row

    host = client.raw.get("host") or origin_of(client.url)
    row["host"] = host
    row["recordedUrl"] = str(client.url)[:120]

    # Inject the caller's prompt into the recorded body (pure string work,
    # proven across capture generations). ONE sentinel substitution — Law 4.
    try:
        new_body = client._inject_prompt(prompt) if client.base_body else None
    except ChatError as e:
        row.update(verdict="BAD_FILE", detail=str(e)[:140], latencyMs=0)
        return row
    if client.base_body and new_body == client.base_body and prompt not in new_body:
        row.update(verdict="BAD_FILE",
                   detail="SENTINEL_NOT_FOUND: no known sentinel in recorded body", latencyMs=0)
        return row

    origin = origin_of(client.url)
    row["runFromOrigin"] = origin
    started = time.perf_counter()
    try:
        sess = tab_cache.get(origin)
        if sess is None:
            sess = get_tab_session(port, pages, origin)
            tab_cache[origin] = sess
        js = build_fetch_js(client.url, client.method, client.headers, new_body, expect)
        res = sess.evaluate(js, timeout=(FETCH_TIMEOUT_MS / 1000) + 30)
    except (CDPError, RuntimeError) as e:
        row.update(verdict="ERROR", detail=f"tab/cdp: {str(e)[:120]}",
                   latencyMs=round((time.perf_counter() - started) * 1000))
        return row

    row["latencyMs"] = round((time.perf_counter() - started) * 1000)

    if not isinstance(res, dict):
        row.update(verdict="ERROR", detail="no result from in-browser fetch", )
        return row
    if not res.get("ok"):
        # TypeError: Failed to fetch = CORS block or network refusal — data,
        # reported honestly. It means the recorded call was NOT same-origin and
        # must be run from the page that originally made it.
        row.update(verdict="ERROR", detail=f"fetch: {str(res.get('error'))[:140]}")
        return row

    status = res.get("status")
    body = res.get("body") or ""
    row["status"] = status
    row["bodyBytes"] = len(body)
    row["contentType"] = (res.get("headers") or {}).get("content-type", "")[:80]

    # THE verdict, spoken in the one protocol every browser shares: did the
    # response body the browser received actually contain the answer phrase?
    if keyword_in_body(body, expect):
        row["verdict"] = "REPLAY_OK"
        row["detail"] = f"in-browser fetch, status {status}, phrase in body ({len(body)}B)"
    else:
        verdict, detail = classify(body, status, None, expect)
        row["verdict"] = verdict
        row["detail"] = detail
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--only", default="", help="comma-separated host/file substrings")
    ap.add_argument("--prompt",
                    default="Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks")
    ap.add_argument("--expect", default="the holy cow jumps over the stricks")
    a = ap.parse_args()

    files = sorted(SECRETS.glob("session_*.json"))
    if a.only:
        want = [s.strip().lower() for s in a.only.split(",") if s.strip()]
        files = [f for f in files if any(w in f.name.lower() for w in want)]
    if not files:
        print(f"no session_*.json in {SECRETS}")
        return 1

    try:
        pages = list_pages(a.port)
    except Exception as e:
        print(f"CDP {a.port} unreachable: {e}")
        return 1
    print(f"browser replay: {len(files)} sessions, executed as fetch() inside the live "
          f"Chrome on :{a.port} ({len(pages)} tabs open)\n")

    rows: list[Dict[str, Any]] = []
    tab_cache: Dict[str, TabSession] = {}
    try:
        for f in files:
            row = replay_one(f, a.port, pages, a.prompt, a.expect, tab_cache)
            rows.append(row)
            mark = "OK " if row["verdict"] == "REPLAY_OK" else "   "
            print(f"  {mark}{row['host'][:32]:32s} {row['verdict']:12s} "
                  f"{row.get('latencyMs', 0):6d}ms  {row.get('detail', '')[:70]}")
    finally:
        for sess in tab_cache.values():
            try:
                sess.close()
            except Exception:
                pass

    ok = sorted({r["host"] for r in rows if r["verdict"] == "REPLAY_OK"})
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport": "in-browser fetch via CDP (the real Chrome network stack, no impersonation)",
        "question": "does a captured request replay when the BROWSER itself sends it?",
        "results": rows,
        "summary": {"replayable": ok,
                    "other": sorted({r["host"] for r in rows if r["verdict"] != "REPLAY_OK"})},
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreplayable ({len(ok)}): {', '.join(ok) or 'none'}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
