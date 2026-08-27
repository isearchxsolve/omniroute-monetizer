# -*- coding: utf-8 -*-
"""chrome_replay_client.py — Chrome-backed pool client (the business bridge).

The pool (:8190 session_pool_shim) historically served harvested sessions by replaying
recorded bytes with Python `requests` (universal_replay). The 2026-08-27 Adapter Thesis
(worklog #1094-#1099) proved that 12 providers can ONLY be served through the live
signed-in Chrome: 9 via in-browser fetch and 3 via adapter invocation. Those providers
were invisible to the pool — real supply sitting unused. This module bridges them.

It implements the EXACT pool client contract (see session_pool._client_for):
    __init__(secret=<path>)          # secret unused; the live Chrome IS the credential
    chat(messages, model, **kw)      # -> {"text": ..., "label": ...}
    raises ChatError / SessionExpired so the pool's cooldown + failover logic applies.

Mechanism (adapter invocation, generalized from adapter_invoke_generic.py):
  1. attach to live Chrome via debuggerAddress (NEVER quit — operator's browser)
  2. focus the tab whose URL contains the provider's UI host
  3. snapshot existing message containers (recency guard)
  4. inject the prompt into the VISIBLE chat input (skip hidden reCAPTCHA textareas —
     the cerebras trap, worklog #1098) via native setter / insertText + input event
  5. trigger the site's own send (Enter; button-click fallback nearest the input)
  6. poll for the answer in a NEW, SHORT container (generic false-positive guard)

Concurrency: ONE Chrome, ONE driver, ONE global lock. The pool's per-host locks spread
load across providers, but every Chrome-backed call still serializes here — correct,
because a single browser can only type in one tab at a time.
"""
from __future__ import annotations

import json
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional

# Raise the SAME exception classes the pool catches (session_pool.py imports ChatError
# from veoaifree_chat_client and SessionExpired from veo_session_replay). Defining local
# lookalikes would slip past the pool's except-clauses and crash the shim instead of
# failing over to the next seat.
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

# ---------------------------------------------------------------- registry ----
# host (as recorded in state/secrets/session_*.json) -> UI tab URL substring.
# API-host recordings (1min, cohere, groq) map to the UI tab that holds the session.
CHROME_CLIENTS: Dict[str, str] = {
    "api.1min.ai": "1min.ai",
    "gemini.google.com": "gemini.google.com",
    "www.perplexity.ai": "perplexity.ai",
    "chat.mistral.ai": "chat.mistral.ai",
    "api.cohere.com": "dashboard.cohere.com",
    "chat.qwen.ai": "chat.qwen.ai",
    "api.groq.com": "console.groq.com",
    "felo.ai": "felo.ai",
    "chatx.ai": "chatx.ai",
    "chat.deepseek.com": "chat.deepseek.com",
    "chatglm.cn": "chatglm.cn",
    "chat.cerebras.ai": "chat.cerebras.ai",
}

CDP_PORT = 9222
# Must stay UNDER Selenium's default 120s HTTP read timeout: execute_async_script holds
# the HTTP connection open for the whole poll, and the urllib3 read timeout (120s) fires
# before the W3C script timeout if they are equal. 90s leaves headroom either side.
ANSWER_TIMEOUT_S = 90

# ------------------------------------------------------- shared driver/lock ----
_DRIVER = None
_DRIVER_LOCK = threading.Lock()   # held for the WHOLE call: one browser, one typist


def _attach():
    global _DRIVER
    if _DRIVER is None:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{CDP_PORT}")
        _DRIVER = webdriver.Chrome(options=opts)
        _DRIVER.set_script_timeout(ANSWER_TIMEOUT_S + 30)
    return _DRIVER


# ------------------------------------------------------------------ JS bits ----
def _visible_guard():
    return r"""
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  function isRecaptcha(el){
    const s = ((el.id||'')+' '+(el.className||'')+' '+(el.name||'')).toLowerCase();
    return s.includes('recaptcha');
  }
"""

SNAP_JS = r"""
(function(runid){
  // Mark every message container that exists RIGHT NOW. The poll treats any container
  // WITHOUT this marker as new. Attribute-marking (not text-dedup) is mandatory: a
  // repeated short answer ("pong" twice) has identical text to an old container and
  // text-dedup would skip the genuine new reply.
  const sels = '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]';
  let n = 0;
  document.querySelectorAll(sels).forEach(el=>{ el.setAttribute('data-crc-seen', runid); n++; });
  return n;
})(arguments[0])
"""

INJECT_JS = r"""
(function(prompt){
%s
  let ta = Array.from(document.querySelectorAll('textarea'))
             .find(el=>visible(el) && !isRecaptcha(el));
  if(ta){
    ta.focus();
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(ta, prompt);
    ta.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'textarea', len:(ta.value||'').length};
  }
  let ce = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]'))
             .find(el=>visible(el));
  if(ce){
    ce.focus();
    let inserted=false;
    try{ inserted=document.execCommand('insertText', false, prompt); }catch(e){}
    if(!inserted){ ce.textContent = prompt; }
    ce.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'contenteditable', len:(ce.innerText||'').length};
  }
  return {ok:false, why:'no visible textarea or contenteditable found'};
})(arguments[0])
""" % _visible_guard()

SEND_JS = r"""
(function(){
%s
  const el = Array.from(document.querySelectorAll('textarea'))
               .find(e=>visible(e)&&!isRecaptcha(e))
            || Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]'))
               .find(e=>visible(e));
  if(!el) return {ok:false, why:'no input'};
  const opts={key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true};
  el.dispatchEvent(new KeyboardEvent('keydown',opts));
  el.dispatchEvent(new KeyboardEvent('keypress',opts));
  el.dispatchEvent(new KeyboardEvent('keyup',opts));
  const left = (el.value!==undefined?el.value:el.innerText)||'';
  return {ok:true, method:'enter', remaining:left.length};
})()
""" % _visible_guard()

CLICK_JS = r"""
(function(){
%s
  const cands = Array.from(document.querySelectorAll('button,[role="button"]'))
    .filter(el=>visible(el) && !el.disabled
      && !/cky-|cookie|consent/i.test((el.className||'')+' '+(el.getAttribute('aria-label')||'')));
  if(!cands.length) return {ok:false, why:'no enabled button'};
  let pick = cands.find(el=>el.getAttribute('type')==='submit')
          || cands.find(el=>/send|submit/i.test((el.getAttribute('aria-label')||'')+(el.getAttribute('data-testid')||'')))
          || null;
  if(!pick){
    const input = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]'))
                    .find(e=>visible(e) && !isRecaptcha(e));
    if(input){
      const ir = input.getBoundingClientRect();
      const cx = ir.x+ir.width/2, cy = ir.y+ir.height/2;
      pick = cands.map(el=>{
        const r = el.getBoundingClientRect();
        return {el, d: Math.hypot(r.x+r.width/2-cx, r.y+r.height/2-cy)};
      }).sort((a,b)=>a.d-b.d)[0].el;
    }
  }
  if(!pick) pick = cands[cands.length-1];
  pick.click();
  return {ok:true, picked:((pick.getAttribute('aria-label')||pick.getAttribute('data-testid')||pick.className||'')+'').replace(/\s+/g,' ').slice(0,60)};
})()
""" % _visible_guard()

POLL_JS = r"""
const prompt = arguments[0];
const runid = arguments[1];
const cb = arguments[2];
const flat = s => (s||'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
const flatPrompt = flat(prompt);
const t0 = Date.now();
let lastText = null, stableCount = 0, bestEl = null;
const timer = setInterval(()=>{
  const seen = new Set();
  const sels = '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]';
  // newest container that (a) was NOT marked by the pre-send snapshot and (b) is not the
  // echoed prompt. Attribute marking survives repeated identical answers ("pong" twice).
  let cand = null;
  document.querySelectorAll(sels).forEach(el=>{
    if(seen.has(el)) return; seen.add(el);
    if(el.getAttribute('data-crc-seen') === runid) return;   // existed before send
    const t=(el.innerText||'').trim();
    if(!t) return;
    const ft = flat(t);
    // skip the user's own bubble: it IS the prompt (possibly with light decoration)
    if(ft === flatPrompt) return;
    if(ft.includes(flatPrompt) && t.length <= prompt.length*1.5) return;
    cand = {el, t};                       // DOM order: last match = newest message
  });
  if(cand){
    if(cand.t === lastText){ stableCount++; }
    else { lastText = cand.t; stableCount = 0; }
    bestEl = cand;
    // stable for 2 consecutive polls (~1.6s) => streaming finished
    if(stableCount >= 2 && lastText){
      clearInterval(timer);
      cb({found:true, ms:Date.now()-t0, text:lastText});
      return;
    }
  }
  if(Date.now()-t0 > TIMEOUT_MS){
    clearInterval(timer);
    if(bestEl && bestEl.t){ cb({found:true, ms:Date.now()-t0, text:bestEl.t, unstable:true}); }
    else { cb({found:false, ms:Date.now()-t0}); }
  }
}, 800);
"""


def _flatten_prompt(messages: List[Dict[str, Any]]) -> str:
    """Chat UIs take ONE text box. Use the last user message; if a system prompt is
    present, prepend it compactly so the seat still honors the contract."""
    sys_txt = " ".join(m.get("content", "") for m in messages if m.get("role") == "system").strip()
    user_txts = [m.get("content", "") for m in messages if m.get("role") == "user"]
    last = user_txts[-1].strip() if user_txts else ""
    if not last:
        raise ChatError("NO_MESSAGES", "no user message to send")
    if sys_txt:
        return f"[Instructions: {sys_txt[:400]}]\n{last}"
    return last


class ChromeReplayClient:
    """Pool client that serves a chat call by driving the provider's own UI inside the
    operator's live signed-in Chrome (adapter invocation)."""

    def __init__(self, secret=None, host: Optional[str] = None, **kw):
        self.secret = pathlib.Path(secret) if secret else None
        raw = {}
        if self.secret and self.secret.exists():
            try:
                raw = json.loads(self.secret.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
        self.host = host or raw.get("host") or ""
        self.tab_substr = CHROME_CLIENTS.get(self.host, self.host)
        self.label = f"chrome/{self.host}"

    # ------------------------------------------------------------- plumbing ----
    def _focus_tab(self, driver):
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                if self.tab_substr in driver.current_url:
                    try:
                        driver.execute_cdp_cmd("Page.bringToFront", {})
                    except Exception:
                        pass
                    return driver.current_url
            except Exception:
                continue
        return None

    # ----------------------------------------------------------------- chat ----
    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
             **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
        prompt = _flatten_prompt(messages)

        with _DRIVER_LOCK:
            try:
                driver = _attach()
            except Exception as e:
                raise ChatError("CHROME_UNAVAILABLE", f"cannot attach to :{CDP_PORT}: {e}")

            url = self._focus_tab(driver)
            if not url:
                # No tab = the seat is not currently open in Chrome. Not an expiry of
                # credentials — the operator can reopen the tab. Fail over cleanly.
                raise ChatError("NO_TAB", f"no open tab matching {self.tab_substr!r}")

            runid = f"crc-{int(time.time()*1000)}"
            driver.execute_script("return " + SNAP_JS.strip(), runid)
            r1 = driver.execute_script("return " + INJECT_JS.strip(), prompt)
            if not r1.get("ok"):
                raise ChatError("NO_INPUT", r1.get("why", "no visible input"))

            r2 = driver.execute_script("return " + SEND_JS.strip())
            time.sleep(2)
            if r2.get("remaining", 0) > 0:
                # Enter did not consume — some apps clear async (chatglm/cerebras), some
                # need a button. Click fallback; the poll below is the arbiter either way.
                driver.execute_script("return " + CLICK_JS.strip())
                time.sleep(2)

            poll = POLL_JS.replace("TIMEOUT_MS", str(ANSWER_TIMEOUT_S * 1000))
            r4 = driver.execute_async_script(poll, prompt, runid)

        if not r4 or not r4.get("found"):
            raise ChatError("NO_ANSWER", f"no reply within {ANSWER_TIMEOUT_S}s")

        text = (r4.get("text") or "").strip()
        if not text:
            raise ChatError("EMPTY_ANSWER", "reply container appeared but stayed empty")
        return {"text": text, "label": self.label,
                "chrome_ms": r4.get("ms"), "tab": url}


# ------------------------------------------------------------- self-test CLI ----
if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "chat.cerebras.ai"
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Reply with exactly one word: pong."
    c = ChromeReplayClient(host=host)
    t0 = time.time()
    try:
        r = c.chat([{"role": "user", "content": prompt}])
        print("OK %dms label=%s text=%r" % (int((time.time() - t0) * 1000), r["label"], r["text"][:120]))
    except (ChatError, SessionExpired) as e:
        print("ERR", e)
        sys.exit(1)
