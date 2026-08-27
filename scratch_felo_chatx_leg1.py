# -*- coding: utf-8 -*-
"""Fire leg-1 for felo + chatx, dump FULL responses to discover the leg-2 answer endpoint.

Both hosts returned 200 + a handle (stream_key / conversions_id) on leg 1; the actual
answer arrives on a follow-up leg that was never recorded. Doctrine: reproduce what
Chrome does. Step 1 = re-fire leg 1 and read the whole response to learn leg 2's shape.

Attach-only via debuggerAddress. NEVER calls driver.quit(). No secrets printed.
"""
import json
import re
import sys
import time
import uuid

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PORT = "127.0.0.1:9222"
SECRETS = r"d:\omniroute-monetizer\state\secrets"
PROMPT = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
TIMEOUT_MS = 60_000

FORBIDDEN = {"host", "content-length", "connection", "accept-encoding", "cookie",
             "origin", "user-agent", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
             "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"}


def attach():
    opts = Options()
    opts.add_experimental_option("debuggerAddress", PORT)
    d = webdriver.Chrome(options=opts)
    d.set_script_timeout(TIMEOUT_MS // 1000 + 30)
    return d


def focus_origin(driver, origin):
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if driver.current_url.startswith(origin):
                driver.execute_cdp_cmd("Page.bringToFront", {})
                return True
        except Exception:
            continue
    driver.switch_to.new_window("tab")
    driver.get(origin + "/")
    time.sleep(4)
    return False


def fire(driver, url, method, headers, body):
    # Pass url/method/headers/body as SCRIPT ARGUMENTS (not string-embedded) so the
    # body reaches fetch() verbatim. String-embedding via json.dumps double-encodes a
    # JSON body and the server then parses a string instead of an object (felo 422).
    js = r"""
    const url = arguments[0], method = arguments[1], headers = arguments[2], body = arguments[3];
    const cb = arguments[4];
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 60000);
    fetch(url, {method: method, headers: headers, body: body, signal: ctrl.signal, credentials: 'include'})
      .then(async r => {
        const text = await r.text();
        clearTimeout(t);
        cb({status: r.status, headers: Object.fromEntries(r.headers.entries()), body: text.slice(0, 200000)});
      })
      .catch(e => { clearTimeout(t); cb({error: String(e)}); });
    """
    return driver.execute_async_script(js, url, method, headers, body)


def clean(headers):
    return {k: v for k, v in headers.items() if k.lower() not in FORBIDDEN}


def do_felo(driver):
    print("\n" + "=" * 60 + "\nFELO leg-1\n" + "=" * 60)
    sess = json.load(open(SECRETS + r"\session_felo_ai_web.json", encoding="utf-8"))
    rx = sess["recorded_exchange"]
    url, method = rx["url"], rx.get("method", "POST")
    headers = clean(dict(rx.get("request_headers", {})))
    body = rx.get("request_body") or ""

    fresh = uuid.uuid4().hex[:21]
    b = json.loads(body)
    b["query"] = PROMPT
    b["search_uuid"] = fresh
    b["process_id"] = fresh
    body = json.dumps(b)
    headers["content-type"] = "application/json"

    focus_origin(driver, "https://felo.ai")
    print("firing from:", driver.current_url)
    res = fire(driver, url, method, headers, body)
    if res.get("error"):
        print("ERROR:", res["error"])
        return
    print("HTTP", res["status"], "content-type:", res["headers"].get("content-type"))
    print("--- BODY (first 3000) ---")
    print(res["body"][:3000])
    open(r"d:\omniroute-monetizer\state\felo_leg1_response.txt", "w", encoding="utf-8").write(res["body"])
    print("\nsaved state/felo_leg1_response.txt")


def do_chatx(driver):
    print("\n" + "=" * 60 + "\nCHATX leg-1\n" + "=" * 60)
    sess = json.load(open(SECRETS + r"\session_chatx.json", encoding="utf-8"))
    rx = sess["recorded_exchange"]
    url, method = rx["url"], rx.get("method", "POST")
    headers = clean(dict(rx.get("request_headers", {})))
    body = rx.get("request_body") or ""

    focus_origin(driver, "https://chatx.ai")
    print("firing from:", driver.current_url)

    # harvest a fresh Laravel CSRF token from the page (meta tag), fall back to cookie
    csrf = driver.execute_script(
        "var m=document.querySelector('meta[name=\"csrf-token\"]');return m?m.content:null;")
    print("meta csrf:", (csrf[:20] + "...") if csrf else None)
    if not csrf:
        m = driver.execute_script(
            "var m=document.cookie.match(/(?:^|;\\s*)XSRF-TOKEN=([^;]+)/);"
            "return m?decodeURIComponent(m[1]):null;")
        csrf = m
        print("cookie XSRF:", (csrf[:20] + "...") if csrf else None)

    if csrf:
        # replace _token in body and X-CSRF-TOKEN header
        body = re.sub(r"_token=[^&]*", "_token=" + csrf, body)
        for k in list(headers.keys()):
            if k.lower() == "x-csrf-token":
                headers[k] = csrf
    # swap the prompt into the form body
    import urllib.parse
    body = re.sub(r"prompt=[^&]*", "prompt=" + urllib.parse.quote(PROMPT, safe=""), body)
    headers["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    headers["x-requested-with"] = "XMLHttpRequest"

    res = fire(driver, url, method, headers, body)
    if res.get("error"):
        print("ERROR:", res["error"])
        return
    print("HTTP", res["status"], "content-type:", res["headers"].get("content-type"))
    print("--- BODY (first 3000) ---")
    print(res["body"][:3000])
    open(r"d:\omniroute-monetizer\state\chatx_leg1_response.txt", "w", encoding="utf-8").write(res["body"])
    print("\nsaved state/chatx_leg1_response.txt")


def main():
    driver = attach()
    print("attached, windows=%d" % len(driver.window_handles))
    try:
        do_felo(driver)
    except Exception as e:
        print("felo exception:", e)
    try:
        do_chatx(driver)
    except Exception as e:
        print("chatx exception:", e)
    print("\nDONE - do NOT quit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
