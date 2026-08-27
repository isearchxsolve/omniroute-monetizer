# -*- coding: utf-8 -*-
"""Groq class-(a) fix: harvest live Stytch JWT from console.groq.com, replay with it.

Doctrine: Chrome's app pulls a fresh bearer from storage at send-time. The recorded
bearer was a short-lived Stytch JWT that expired. We extract the live one and re-fire.

Attach-only via debuggerAddress. NEVER calls driver.quit(). No secrets printed.
"""
import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PORT = "127.0.0.1:9222"
SESSION_FILE = r"d:\omniroute-monetizer\state\secrets\session_groq_chat.json"
EXPECT = "the holy cow jumps over the stricks"
PROMPT = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
FETCH_TIMEOUT_MS = 90_000


def main() -> int:
    with open(SESSION_FILE, encoding="utf-8") as f:
        sess = json.load(f)
    rx = sess["recorded_exchange"]
    url = rx["url"]
    method = rx.get("method", "POST")
    headers = dict(rx.get("request_headers", {}))
    body = rx.get("request_body") or ""

    # swap the sentinel prompt into the body
    try:
        b = json.loads(body)
        if isinstance(b, dict) and isinstance(b.get("messages"), list):
            for m in b["messages"]:
                if m.get("role") == "user":
                    m["content"] = PROMPT
            body = json.dumps(b)
    except Exception as e:
        print("body rewrite skipped: %s" % e)

    opts = Options()
    opts.add_experimental_option("debuggerAddress", PORT)
    driver = webdriver.Chrome(options=opts)
    driver.set_script_timeout(FETCH_TIMEOUT_MS // 1000 + 30)
    print("attached, windows=%d" % len(driver.window_handles))

    # find or open console.groq.com tab (same origin as Referer)
    tab = None
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "console.groq.com" in driver.current_url:
                tab = h
                break
        except Exception:
            continue
    if tab is None:
        driver.switch_to.new_window("tab")
        driver.get("https://console.groq.com/")
        time.sleep(5)
    else:
        driver.execute_cdp_cmd("Page.bringToFront", {})
    print("on tab: %s" % driver.current_url)

    # 1) harvest the live Stytch JWT (cookie first, then localStorage SDK state)
    harvest_js = r"""
    const cb = arguments[arguments.length - 1];
    const out = {jwt: null, source: null};
    try {
      const m = document.cookie.match(/(?:^|;\s*)stytch_session_jwt=([^;]+)/);
      if (m && m[1]) { out.jwt = decodeURIComponent(m[1]); out.source = 'cookie:stytch_session_jwt'; }
    } catch (e) {}
    if (!out.jwt) {
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.indexOf('stytch_sdk_state') === 0 && k.indexOf('::') === -1) {
            const v = localStorage.getItem(k) || '';
            const jm = v.match(/"session_jwt"\s*:\s*"([^"]+)"/);
            if (jm && jm[1]) { out.jwt = jm[1]; out.source = 'localStorage:' + k; break; }
            const jm2 = v.match(/"jwt"\s*:\s*"([^"]+)"/);
            if (jm2 && jm2[1]) { out.jwt = jm2[1]; out.source = 'localStorage:' + k; break; }
          }
        }
      } catch (e) {}
    }
    cb(out);
    """
    hv = driver.execute_async_script(harvest_js)
    if not hv.get("jwt"):
        print("NO LIVE JWT FOUND - cannot fix class (a). source=%s" % hv.get("source"))
        return 1
    jwt = hv["jwt"]
    print("harvested live JWT from %s (len=%d, prefix=%s...)" % (hv["source"], len(jwt), jwt[:20]))

    # 2) build headers with fresh bearer
    headers["authorization"] = "Bearer " + jwt
    # drop forbidden / hop headers
    forbidden = {"host", "content-length", "connection", "accept-encoding", "cookie",
                 "origin", "referer", "user-agent", "sec-fetch-site", "sec-fetch-mode",
                 "sec-fetch-dest", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"}
    send_headers = {k: v for k, v in headers.items() if k.lower() not in forbidden}
    send_headers["content-type"] = "application/json"
    send_headers["accept"] = "application/json"

    # 3) fire fetch from the console origin (same-origin to avoid CORS preflight issues)
    fetch_js = r"""
    const cb = arguments[arguments.length - 1];
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    fetch(URL, {method: METHOD, headers: HEADERS, body: BODY, signal: ctrl.signal, credentials: 'include'})
      .then(async r => {
        const text = await r.text();
        clearTimeout(t);
        cb({status: r.status, body: text.slice(0, 4000000)});
      })
      .catch(e => { clearTimeout(t); cb({error: String(e)}); });
    """
    fetch_js = (fetch_js
                .replace("TIMEOUT_MS", str(FETCH_TIMEOUT_MS))
                .replace("URL", json.dumps(url))
                .replace("METHOD", json.dumps(method))
                .replace("HEADERS", json.dumps(send_headers))
                .replace("BODY", json.dumps(body)))
    res = driver.execute_async_script(fetch_js)

    # CORS fallback: fire from a tab on the API's own origin (same-origin => no preflight)
    if res.get("error") and "Failed to fetch" in str(res.get("error")):
        print("CORS block from console origin -> falling back to api-origin tab")
        orig_tab = driver.current_window_handle
        driver.switch_to.new_window("tab")
        driver.get("https://api.groq.com/openai/v1/models")
        time.sleep(3)
        res = driver.execute_async_script(fetch_js)
        driver.close()
        driver.switch_to.window(orig_tab)

    if res.get("error"):
        print("FETCH ERROR: %s" % res["error"])
        return 1
    status = res.get("status")
    rbody = res.get("body", "")
    print("HTTP %s, body_len=%d" % (status, len(rbody)))

    # verdict: keyword check on raw + SSE content concatenation
    import re
    def kw(text):
        flat = re.sub(r"[^a-z ]", " ", text.lower())
        flat = re.sub(r"\s+", " ", flat).strip()
        return EXPECT.lower() in flat

    def sse_content(text):
        # OpenAI-style SSE: concatenate delta.content fragments with NO separator
        # (they are contiguous pieces of the final text; a space join breaks mid-word splits)
        parts = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                continue
            try:
                d = json.loads(payload)
            except Exception:
                continue
            for c in d.get("choices", []):
                dl = c.get("delta", {}) or {}
                if dl.get("content"):
                    parts.append(dl["content"])
        return "".join(parts)

    def aggregated(text):
        parts = re.findall(r'"(?:text|value|content|message|delta|answer|reply)"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.I)
        out = []
        for p in parts:
            try:
                out.append(json.loads('"' + p + '"'))
            except Exception:
                out.append(p)
        return " ".join(out)

    content_stream = sse_content(rbody)
    if kw(rbody):
        print("REPLAY_OK (raw keyword match)")
        verdict = "REPLAY_OK"
    elif kw(content_stream):
        print("REPLAY_OK (via SSE content concatenation)")
        verdict = "REPLAY_OK"
    elif kw(aggregated(rbody)):
        print("REPLAY_OK (via frame aggregation)")
        verdict = "REPLAY_OK"
    else:
        verdict = "FAIL"
        print("FAIL - content_stream=%r" % content_stream[:300])
        print("FAIL - body preview:")
        print(rbody[:1200])

    # persist result
    out = {
        "host": "api.groq.com",
        "verdict": verdict,
        "status": status,
        "jwtSource": hv["source"],
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(r"d:\omniroute-monetizer\state\groq_live_bearer_replay.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    with open(r"d:\omniroute-monetizer\state\groq_last_body.txt", "w", encoding="utf-8") as f:
        f.write(rbody)
    print("saved state/groq_live_bearer_replay.json + state/groq_last_body.txt")
    print("DONE - do NOT quit.")
    return 0 if verdict == "REPLAY_OK" else 2


if __name__ == "__main__":
    sys.exit(main())
