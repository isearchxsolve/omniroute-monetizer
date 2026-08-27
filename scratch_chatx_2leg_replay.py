# -*- coding: utf-8 -*-
"""CHATX full 2-leg replay (doctrine class-a fix).

Leg 1: POST /sendchat (form, Laravel _token CSRF) -> returns conversions_id + ass_conversions_id.
Leg 2: GET  /chats_stream?user_id=&chats_id=&current_model=&conversions_id=&ass_conversions_id=
       &g_recaptcha_response=&is_web=&is_youtube=&reasoning_effort=&verbosity=   (SSE EventSource).

Discovered from chatx's own inline JS:
  new EventSource(locale+"chats_stream?user_id="+e+"&chats_id="+t+"&current_model="+a
    +"&conversions_id="+s+"&ass_conversions_id="+i+"&g_recaptcha_response="+o
    +"&is_web="+is_web+"&is_youtube="+is_youtube+"&reasoning_effort="+..+"&verbosity="+..)
  Stream parse: first msg has conversions_id; then type=="response.output_text.delta" -> y+=d.delta.

Body handling: surgical regex edits on the RAW recorded form body (fresh _token + prompt).
Attach-only via debuggerAddress. NEVER calls driver.quit(). No secrets printed.
"""
import json
import re
import sys
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PORT = "127.0.0.1:9222"
SESSION_FILE = r"d:\omniroute-monetizer\state\secrets\session_chatx.json"
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


def focus_chatx(driver):
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if driver.current_url.startswith("https://chatx.ai"):
                driver.execute_cdp_cmd("Page.bringToFront", {})
                return
        except Exception:
            continue
    driver.switch_to.new_window("tab")
    driver.get("https://chatx.ai/gpt")
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

    driver = attach()
    print("attached, windows=%d" % len(driver.window_handles))
    focus_chatx(driver)
    print("on:", driver.current_url)

    # fresh Laravel CSRF from the page meta tag
    csrf = driver.execute_script(
        "var m=document.querySelector('meta[name=\"csrf-token\"]');return m?m.content:null;")
    if not csrf:
        print("no csrf meta - cannot build leg 1")
        return 1
    print("fresh csrf:", csrf[:20] + "...")

    # surgical edits on the RAW form body
    body = re.sub(r"_token=[^&]*", "_token=" + urllib.parse.quote(csrf, safe=""), body, count=1)
    body = re.sub(r"prompt=[^&]*", "prompt=" + urllib.parse.quote(PROMPT, safe=""), body, count=1)
    for k in list(headers.keys()):
        if k.lower() == "x-csrf-token":
            headers[k] = csrf
    headers["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    headers["x-requested-with"] = "XMLHttpRequest"

    # parse the fixed params we need for leg 2
    params = dict(urllib.parse.parse_qsl(body))
    user_id = params.get("user_id", "")
    chats_id = params.get("chats_id", "")
    current_model = params.get("current_model", "gpt3")
    is_web = params.get("is_web", "0")
    is_youtube = params.get("is_youtube", "0")

    # ---- LEG 1 ----
    print("\n--- LEG 1: POST /sendchat ---")
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
        j1 = json.loads(b1)
    except Exception:
        print("leg1 body not JSON")
        return 1
    if not j1.get("response"):
        print("leg1 response=false:", j1.get("message") or j1.get("error"))
        return 1
    conversions_id = j1.get("conversions_id")
    ass_conversions_id = j1.get("ass_conversions_id")
    print("conversions_id:", conversions_id, "ass:", ass_conversions_id)

    # ---- LEG 2 ----
    print("\n--- LEG 2: GET /chats_stream (SSE) ---")
    q = urllib.parse.urlencode({
        "user_id": user_id, "chats_id": chats_id, "current_model": current_model,
        "conversions_id": conversions_id, "ass_conversions_id": ass_conversions_id,
        "g_recaptcha_response": "", "is_web": is_web, "is_youtube": is_youtube,
        "reasoning_effort": "", "verbosity": "",
    })
    leg2_url = "https://chatx.ai/chats_stream?" + q

    leg2_js = r"""
    const url=arguments[0], expect=arguments[1], cb=arguments[2];
    const ctrl=new AbortController();
    const t=setTimeout(()=>ctrl.abort(), LEG2_TIMEOUT_MS);
    (async()=>{
      try{
        const r=await fetch(url,{method:'GET',credentials:'include',signal:ctrl.signal,headers:{Accept:'text/event-stream'}});
        if(!r.ok||!r.body){clearTimeout(t);cb({status:r.status,body:(await r.text()).slice(0,200000)});return;}
        const reader=r.body.getReader();
        const dec=new TextDecoder();
        let acc='', deltas='';
        const flat=s=>s.toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
        const want=flat(expect);
        while(true){
          const {done,value}=await reader.read();
          if(done)break;
          const chunk=dec.decode(value,{stream:true});
          acc+=chunk;
          // parse SSE data: lines, each may be JSON with type/delta
          for(const line of chunk.split('\n')){
            const ln=line.trim();
            if(!ln.startsWith('data:'))continue;
            const payload=ln.slice(5).trim();
            if(!payload||payload==='[DONE]')continue;
            try{
              const d=JSON.parse(payload);
              if(d.type==='response.output_text.delta'&&d.delta)deltas+=d.delta;
              else if(typeof d.delta==='string')deltas+=d.delta;
              else if(typeof d.text==='string')deltas+=d.text;
              else if(typeof d.message==='string')deltas+=d.message;
            }catch(e){}
          }
          if(flat(deltas).includes(want)||flat(acc).includes(want)){
            clearTimeout(t);try{reader.cancel();}catch(e){}
            cb({status:r.status,body:acc.slice(0,200000),deltas:deltas,early:true});return;
          }
          if(acc.length>1500000)break;
        }
        clearTimeout(t);cb({status:r.status,body:acc.slice(0,200000),deltas:deltas});
      }catch(e){clearTimeout(t);cb({error:String(e)});}
    })();
    """
    leg2_js = leg2_js.replace("LEG2_TIMEOUT_MS", str(LEG2_TIMEOUT_MS))
    res2 = driver.execute_async_script(leg2_js, leg2_url, EXPECT)

    if res2.get("error"):
        print("LEG2 ERROR:", res2["error"])
        return 1
    b2 = res2.get("body", "")
    deltas = res2.get("deltas", "")
    print("LEG2 HTTP", res2.get("status"), "early:", res2.get("early"),
          "body_len:", len(b2), "deltas_len:", len(deltas))
    open(r"d:\omniroute-monetizer\state\chatx_leg2_stream.txt", "w", encoding="utf-8").write(b2)

    if kw(deltas) or kw(b2):
        print("\nREPLAY_OK (chatx 2-leg, phrase found in SSE deltas)")
        print("deltas:", repr(deltas[:200]))
        verdict = "REPLAY_OK"
    else:
        print("\nFAIL - phrase not found. deltas preview:", repr(deltas[:300]))
        print("raw preview:", b2[:800])
        verdict = "FAIL"

    out = {"host": "chatx.ai", "verdict": verdict, "leg1Status": res1["status"],
           "leg2Status": res2.get("status"), "conversionsId": conversions_id,
           "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(out, open(r"d:\omniroute-monetizer\state\chatx_2leg_replay.json", "w", encoding="utf-8"), indent=2)
    print("saved state/chatx_2leg_replay.json + state/chatx_leg2_stream.txt")
    print("DONE - do NOT quit.")
    return 0 if verdict == "REPLAY_OK" else 2


if __name__ == "__main__":
    sys.exit(main())
