# -*- coding: utf-8 -*-
"""FELO full 2-leg replay (doctrine class-a fix).

Leg 1: POST /api-proxy/main/search/threads/{short_id}/question  -> returns stream_key.
Leg 2: GET  /api/message/v1/stream/{stream_key}?offset=0        -> SSE stream with answer.

Discovered from felo's own JS bundles:
  - leg-2 URL:  `${base}/api/message/v1/stream/${encodeURIComponent(stream_key)}?offset=${o}`
  - leg-2 hdrs: {Accept:"text/event-stream", Authorization:<same bearer>}, credentials:include

Body handling: surgical regex edits on the RAW recorded body string (no json.loads/dumps
re-serialization, which double-encoded and caused a 422). Send exactly what Chrome sends.

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
SESSION_FILE = r"d:\omniroute-monetizer\state\secrets\session_felo_ai_web.json"
PROMPT = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
EXPECT = "the holy cow jumps over the stricks"
LEG2_TIMEOUT_MS = 90_000

FORBIDDEN = {"host", "content-length", "connection", "accept-encoding", "cookie",
             "origin", "user-agent", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
             "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"}


def attach():
    opts = Options()
    opts.add_experimental_option("debuggerAddress", PORT)
    d = webdriver.Chrome(options=opts)
    d.set_script_timeout(LEG2_TIMEOUT_MS // 1000 + 30)
    return d


def focus_felo(driver):
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if driver.current_url.startswith("https://felo.ai"):
                driver.execute_cdp_cmd("Page.bringToFront", {})
                return
        except Exception:
            continue
    driver.switch_to.new_window("tab")
    driver.get("https://felo.ai/")
    time.sleep(4)


def fire(driver, url, method, headers, body):
    js = r"""
    const url=arguments[0], method=arguments[1], headers=arguments[2], body=arguments[3], cb=arguments[4];
    fetch(url,{method,headers,body,credentials:'include'})
      .then(async r=>cb({status:r.status, headers:Object.fromEntries(r.headers.entries()), body:(await r.text()).slice(0,200000)}))
      .catch(e=>cb({error:String(e)}));
    """
    return driver.execute_async_script(js, url, method, headers, body)


def kw(text):
    flat = re.sub(r"[^a-z ]", " ", (text or "").lower())
    flat = re.sub(r"\s+", " ", flat).strip()
    return EXPECT.lower() in flat


def main():
    sess = json.load(open(SESSION_FILE, encoding="utf-8"))
    rx = sess["recorded_exchange"]
    url, method = rx["url"], rx.get("method", "POST")
    headers = {k: v for k, v in (rx.get("request_headers") or {}).items()
               if k.lower() not in FORBIDDEN}
    body = rx.get("request_body") or ""
    bearer = headers.get("Authorization") or headers.get("authorization")

    # surgical edits on the RAW body string (keep everything else byte-identical)
    fresh = uuid.uuid4().hex[:21]
    body = re.sub(r'"query"\s*:\s*"[^"]*"', '"query":' + json.dumps(PROMPT), body, count=1)
    body = re.sub(r'"search_uuid"\s*:\s*"[^"]*"', '"search_uuid":"' + fresh + '"', body, count=1)
    body = re.sub(r'"process_id"\s*:\s*"[^"]*"', '"process_id":"' + fresh + '"', body, count=1)

    driver = attach()
    print("attached, windows=%d" % len(driver.window_handles))
    focus_felo(driver)
    print("on:", driver.current_url)

    # ---- LEG 1 ----
    print("\n--- LEG 1: POST question ---")
    res1 = fire(driver, url, method, headers, body)
    if res1.get("error"):
        print("LEG1 ERROR:", res1["error"])
        return 1
    print("LEG1 HTTP", res1["status"])
    b1 = res1.get("body", "")
    print("LEG1 body:", b1[:400])
    if res1["status"] != 200:
        print("LEG1 not 200 - stopping")
        return 1
    try:
        stream_key = json.loads(b1).get("stream_key")
    except Exception:
        m = re.search(r'"stream_key"\s*:\s*"([^"]+)"', b1)
        stream_key = m.group(1) if m else None
    if not stream_key:
        print("no stream_key in leg-1 response")
        return 1
    print("stream_key:", stream_key)

    # ---- LEG 2 ----
    print("\n--- LEG 2: GET SSE stream ---")
    leg2_url = "https://felo.ai/api/message/v1/stream/" + stream_key + "?offset=0"
    leg2_headers = {"Accept": "text/event-stream"}
    if bearer:
        leg2_headers["Authorization"] = bearer

    # read the SSE stream incrementally, early-exit when the phrase appears
    leg2_js = r"""
    const url=arguments[0], headers=arguments[1], expect=arguments[2], cb=arguments[3];
    const ctrl=new AbortController();
    const t=setTimeout(()=>ctrl.abort(), LEG2_TIMEOUT_MS);
    (async()=>{
      try{
        const r=await fetch(url,{method:'GET',headers,credentials:'include',signal:ctrl.signal});
        if(!r.ok||!r.body){clearTimeout(t);cb({status:r.status,body:(await r.text()).slice(0,200000)});return;}
        const reader=r.body.getReader();
        const dec=new TextDecoder();
        let acc='';
        const flat=s=>s.toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
        const want=flat(expect);
        while(true){
          const {done,value}=await reader.read();
          if(done)break;
          acc+=dec.decode(value,{stream:true});
          if(flat(acc).includes(want)){clearTimeout(t);try{reader.cancel();}catch(e){}cb({status:r.status,body:acc.slice(0,200000),early:true});return;}
          if(acc.length>1500000)break;
        }
        clearTimeout(t);cb({status:r.status,body:acc.slice(0,200000)});
      }catch(e){clearTimeout(t);cb({error:String(e)});}
    })();
    """
    leg2_js = leg2_js.replace("LEG2_TIMEOUT_MS", str(LEG2_TIMEOUT_MS))
    res2 = driver.execute_async_script(leg2_js, leg2_url, leg2_headers, EXPECT)

    if res2.get("error"):
        print("LEG2 ERROR:", res2["error"])
        return 1
    b2 = res2.get("body", "")
    print("LEG2 HTTP", res2.get("status"), "early_exit:", res2.get("early"), "body_len:", len(b2))
    open(r"d:\omniroute-monetizer\state\felo_leg2_stream.txt", "w", encoding="utf-8").write(b2)

    if kw(b2):
        print("\nREPLAY_OK (felo 2-leg, phrase found in SSE stream)")
        verdict = "REPLAY_OK"
    else:
        print("\nFAIL - phrase not found. stream preview:")
        print(b2[:1500])
        verdict = "FAIL"

    out = {"host": "felo.ai", "verdict": verdict, "leg1Status": res1["status"],
           "leg2Status": res2.get("status"), "streamKey": stream_key,
           "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(out, open(r"d:\omniroute-monetizer\state\felo_2leg_replay.json", "w", encoding="utf-8"), indent=2)
    print("saved state/felo_2leg_replay.json + state/felo_leg2_stream.txt")
    print("DONE - do NOT quit.")
    return 0 if verdict == "REPLAY_OK" else 2


if __name__ == "__main__":
    sys.exit(main())
