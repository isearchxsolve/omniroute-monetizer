#!/usr/bin/env python3
"""playwright_browser_replay.py — Replay captured sessions using Playwright Python.

Connects to live Chrome on seat1 (:9222) via Playwright Chromium CDP adapter.
Executes each session request within real browser page contexts, leveraging
Chrome's native network stack, cookies, and security context.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse
from typing import Any, Dict, Optional

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECRETS = ROOT / "state" / "secrets"
OUT = ROOT / "state" / "playwright_browser_replay.json"

sys.path.insert(0, str(HERE))

from playwright.sync_api import sync_playwright
from universal_replay import UniversalSessionClient, ChatError
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


def inject_prompt_extended(client: UniversalSessionClient, prompt: str) -> str:
    if not client.base_body:
        return ""
    body = client.base_body
    
    # Try standard universal_replay prompt injection first
    injected = client._inject_prompt(prompt)
    if prompt in injected or json.dumps(prompt)[1:-1] in injected:
        return injected

    # Extended sentinel replacement if standard sentinels were not present
    import urllib.parse
    esc = json.dumps(prompt)[1:-1]
    
    extended_phrases = [
        "Omni sentinel shot: a lone lighthouse beam sweeping across dark ocean waves at midnight",
        "Omni sentinel shot",
        "Omni.",
        "Omni",
    ]
    for ph in extended_phrases:
        if ph in body:
            return body.replace(ph, esc if ('{"' in body or body.startswith("{")) else prompt)
        ph_url = urllib.parse.quote_plus(ph)
        if ph_url in body:
            return body.replace(ph_url, urllib.parse.quote_plus(esc))

    return injected


def replay_session_pw(file_path: pathlib.Path, context: Any, prompt: str, expect: str) -> Dict[str, Any]:
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

    # Find existing page matching origin or create new page
    target_page = None
    for p in context.pages:
        try:
            if origin_of(p.url) == origin:
                target_page = p
                break
        except Exception:
            continue

    created_page = False
    if target_page is None:
        try:
            target_page = context.new_page()
            target_page.goto(origin + "/", timeout=15000, wait_until="domcontentloaded")
            created_page = True
        except Exception as e:
            row.update(verdict="ERROR", detail=f"Playwright navigation failed: {str(e)[:100]}", latencyMs=0)
            return row

    started = time.perf_counter()
    try:
        js = build_fetch_js(client.url, client.method, client.headers, new_body, expect)
        res = target_page.evaluate(js)
    except Exception as e:
        row.update(verdict="ERROR", detail=f"Playwright evaluate failed: {str(e)[:120]}",
                   latencyMs=round((time.perf_counter() - started) * 1000))
        if created_page:
            try: target_page.close()
            except Exception: pass
        return row

    if created_page:
        try: target_page.close()
        except Exception: pass

    row["latencyMs"] = round((time.perf_counter() - started) * 1000)

    if not isinstance(res, dict):
        row.update(verdict="ERROR", detail="No result from Playwright fetch")
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
        row["detail"] = f"Playwright Python fetch status {status}, phrase verified ({len(body)}B)"
    else:
        verdict, detail = classify(body, status, None, expect)
        row["verdict"] = verdict
        row["detail"] = detail

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

    print(f"Initializing Playwright Python CDP connection on port {a.port}...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}")
            context = browser.contexts[0]
        except Exception as e:
            print(f"Failed to connect Playwright Python over CDP on :{a.port}: {e}")
            return 1

        print(f"Playwright Python active. Open pages in context: {len(context.pages)}\n")
        rows: list[Dict[str, Any]] = []
        for f in files:
            row = replay_session_pw(f, context, a.prompt, a.expect)
            rows.append(row)
            mark = "OK " if row["verdict"] == "REPLAY_OK" else "   "
            print(f"  {mark}{row['host'][:32]:32s} {row['verdict']:12s} "
                  f"{row.get('latencyMs', 0):6d}ms  {row.get('detail', '')[:70]}")

    ok = sorted({r["host"] for r in rows if r["verdict"] == "REPLAY_OK"})
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport": "Playwright Python connect_over_cdp (real Chromium context)",
        "question": "Does captured session replay when Playwright Python controls the real browser?",
        "results": rows,
        "summary": {
            "replayable": ok,
            "other": sorted({r["host"] for r in rows if r["verdict"] != "REPLAY_OK"})
        }
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReplayable ({len(ok)}): {', '.join(ok) or 'none'}")
    print(f"Wrote report to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
