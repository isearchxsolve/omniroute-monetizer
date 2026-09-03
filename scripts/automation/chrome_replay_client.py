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
    # 2026-08-27 tab-coverage sweep (worklog #1105): signed-in tabs with no seat.
    # All verified signed-in (composer present, no login CTA) in the :9222 providers
    # profile before wiring. The live tab IS the credential — no recorded bytes.
    "copilot.microsoft.com": "copilot.microsoft.com",
    "claude.ai": "claude.ai",
    "grok.com": "grok.com",
    "duck.ai": "duck.ai",
    "genspark.ai": "genspark.ai",
    "v0.app": "v0.app",
    "yi.baichuan-ai.com": "baichuan-ai.com",
    # 2026-08-28 Track 1 (worklog #1116): meta.ai's recorded_exchange is a
    # searchConversations GraphQL query (a conversation-search, NOT a send mutation) —
    # replaying it returns a JSON envelope, a false green. Route to Chrome (live tab is
    # signed in) until a genuine send-mutation blueprint is captured.
    "www.meta.ai": "www.meta.ai",
}

# Per-host response-container selector override for LISTEN_JS. The generic selector set
# works for most hosts, but some UIs put toolbar chrome in elements that also match
# (e.g. Copilot's "Edit in a page" action bar matches [class*="message"]). When a host
# has a stable, specific reply selector, override here. worklog #1105.
RESPONSE_SELECTORS: Dict[str, str] = {
    # Copilot reply body: <div data-testid="ai-message-body">Omni</div> — verified in
    # DOM after sentinel send. The outer [data-content="ai-message"] includes the
    # "Edit in a page" toolbar; the -body node is the clean text.
    "copilot.microsoft.com": '[data-testid="ai-message-body"]',
    # Grok reply body: <div class="... response-content-markdown markdown chat-md ...">.
    # The generic set also matches a "2 / 2" pagination counter that can appear AFTER
    # the reply in DOM order, so the poll returned the counter instead of the answer.
    # Target the markdown body specifically. worklog #1105.
    "grok.com": '[class*="response-content-markdown"]',
    # 1min.ai reply body: <div class="sc-eQaGpr fcvDAV prose prose-sm prose-neutral
    # dark:prose-invert">58</div> — the styled markdown body inside the reply card.
    # The generic set has no match on 1min's styled-components DOM, so the listener
    # polled forever while the answer was already rendered (measured 2026-09-04:
    # screenshot shows "58" from Qwen3 VL 8B while LISTEN returned found=False).
    # Also exclude the chat-composer landing surface: the real chat UI lives at
    # /chat-with-ai (Multi AI Chat), reached by clicking the sidebar item.
    "api.1min.ai": ".prose",
}

# Per-host tab URL substrings to EXCLUDE when focusing. Some hosts open several tab
# types and only one is the chat surface. worklog #1105.
TAB_EXCLUDES: Dict[str, List[str]] = {
    # Copilot's /pages/ view is a document tool: composer id '_r_ia_', no chat message
    # DOM, so the bridge types into it and polls forever (NO_ANSWER). Land on a
    # /chats/ (or home) tab instead. Verified 2026-08-27: 1x /pages/ + 4x /chats/ tabs.
    "copilot.microsoft.com": ["/pages/"],
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
  const sels = '__RESPONSE_SELECTORS__';
  let n = 0;
  document.querySelectorAll(sels).forEach(el=>{ el.setAttribute('data-crc-seen', runid); n++; });
  return n;
})(arguments[0])
"""

# Default generic response-container selector set, shared by SNAP_JS and LISTEN_JS.
DEFAULT_RESPONSE_SELECTORS = (
    '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],'
    '[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]')

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
    // REPLACE, never append. A leftover prompt from a previous run sitting in the
    // composer would otherwise get duplicated in front of the new one (worklog #1123:
    // gemini contenteditable appended the new prompt to the stale sweep prompt).
    // Select-all first so insertText overwrites the existing content.
    try{
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(ce);
      sel.removeAllRanges();
      sel.addRange(range);
    }catch(e){}
    let inserted=false;
    try{ inserted=document.execCommand('insertText', false, prompt); }catch(e){}
    if(!inserted){ ce.textContent = prompt; }
    ce.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok:true, kind:'contenteditable', len:(ce.innerText||'').length};
  }
  return {ok:false, why:'no visible textarea or contenteditable found'};
})(arguments[0])
""" % _visible_guard()

# THE COMPOSER IS THE HUMAN PART OF THE PLAY (operator correction 2026-08-28) -- it is
# neither Chrome's part nor the provider's. The prompt must arrive the way a human's
# does: as a real IME-level edit delivered through Chrome's input pipeline (CDP
# Input.insertText). DOM text surgery (setting value/textContent) writes into a place
# no real actor touches: editor state machines (meta.ai's Lexical, grok's editor, ...)
# only accept input that arrives as genuine input events -- DOM-injected text shows in
# the DOM but the provider's JS reads its own state (empty) and sends nothing. That is
# exactly how meta.ai returned NO_ANSWER while the capture instrument, which types via
# Input.insertText, got a real "Omni" answer back.
#
# FOCUS_JS therefore only LOCATES and FOCUSES the composer (and selects any stale
# content so the IME edit replaces it, like a human Ctrl+A). The typing itself happens
# through Chrome in chat(). INJECT_JS above is kept only as a fallback for the rare
# editor that refuses IME edits.
FOCUS_JS = r"""
(function(){
%s
  let el = Array.from(document.querySelectorAll('textarea'))
             .find(el=>visible(el) && !isRecaptcha(el));
  let kind = 'textarea';
  if(!el){
    el = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"],[contenteditable=""]'))
           .find(el=>visible(el));
    kind = 'contenteditable';
  }
  if(!el) return {ok:false, why:'no visible textarea or contenteditable found'};
  el.scrollIntoView({block:'center'});
  el.focus();
  try{
    if(el.tagName==='TEXTAREA' || el.tagName==='INPUT'){ if(el.select) el.select(); }
    else{
      const sel = window.getSelection();
      if(sel){ const r = document.createRange(); r.selectNodeContents(el); sel.removeAllRanges(); sel.addRange(r); }
    }
  }catch(e){}
  return {ok:true, kind:kind};
})()
""" % _visible_guard()

# Reads back whatever the focused composer now holds (pierces shadow roots, because
# document.activeElement stops at the shadow host).
READ_ACTIVE_JS = r"""
(function(){
  let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  if (!a) return { ok:false, text:'' };
  const t = ('value' in a && typeof a.value === 'string') ? a.value : (a.innerText || a.textContent || '');
  return { ok:true, text:String(t).slice(0, 400) };
})()
"""

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

LISTEN_JS = r"""
// LISTEN, never poll (operator directive 2026-08-28): the provider's own JS renders the
// answer into the DOM, and that render IS a DOM mutation. A MutationObserver fires exactly
// when it happens -- no setInterval asking Chrome "is it there yet?" on a timer. Stream
// completion is a debounce that only arms AFTER a render event and only fires when the
// events go quiet; it confirms silence, it never discovers content.
const prompt = arguments[0];
const runid = arguments[1];
const cb = arguments[2];
const flat = s => (s||'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
const flatPrompt = flat(prompt);
// Transient loading placeholders (v0 "Thinking..."/"Cooking...", grok "Thinking about
// your request", etc.). These are NOT answers -- they are the provider's own "still
// working" UI. Never delivered as the reply; keep listening until real content replaces
// them. Short-text guard so a genuine one-word answer is never mistaken for a placeholder.
// 2026-08-28 fleet sweep: v0.app returned "Cooking..." as a false green because "cooking"
// was missing from this list -- the quiet-debounce armed on the placeholder render.
// v0 cycles several status verbs (Thinking/Cooking/Sending/...), so the list covers the
// whole family. The regex only matches a SINGLE status word (+ optional "about your
// request"), so a genuine one-word answer can never be swallowed.
const PLACEHOLDER_RE = /^(thinking|generating|typing|working|drafting|reasoning|searching|loading|processing|waiting|cooking|creating|building|running|sending|streaming|composing|analyzing|planning|coding|executing)( about( your)? request)?[.\s…]*$/i;
const isPlaceholder = t => t.length <= 48 && PLACEHOLDER_RE.test(t.trim());
const sels = '__RESPONSE_SELECTORS__';
const QUIET_MS = 1200;   // no render event for this long after the last one => stream done
const t0 = Date.now();
let done = false, lastText = null, bestEl = null, quietTimer = null, hardTimer = null;

function finish(payload){
  if(done) return; done = true;
  try{ observer.disconnect(); }catch(e){}
  if(quietTimer) clearTimeout(quietTimer);
  if(hardTimer) clearTimeout(hardTimer);
  cb(payload);
}

function candidate(){
  // Newest container that (a) was NOT marked by the pre-send snapshot and (b) is not the
  // echoed prompt. Attribute marking survives repeated identical answers ("pong" twice).
  const seen = new Set();
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
  return cand;
}

function onRender(){
  // Fired by DOM mutations: the provider's JS just rendered/updated something. Re-read
  // the newest reply container.
  const cand = candidate();
  if(!cand) return;
  bestEl = cand;
  if(isPlaceholder(cand.t)){ lastText = null; return; }   // still working; keep listening
  if(cand.t !== lastText){
    lastText = cand.t;
    if(quietTimer) clearTimeout(quietTimer);
    quietTimer = setTimeout(()=>{
      finish({found:true, ms:Date.now()-t0, text:lastText});
    }, QUIET_MS);
  }
}

// Coalesce mutation bursts into one check per animation frame -- still event-driven (runs
// BECAUSE a mutation happened), never a discovery timer.
let scheduled = false;
const observer = new MutationObserver(()=>{
  if(scheduled) return; scheduled = true;
  requestAnimationFrame(()=>{ scheduled = false; if(!done) onRender(); });
});
observer.observe(document.body, {childList:true, subtree:true, characterData:true});

hardTimer = setTimeout(()=>{
  if(bestEl && bestEl.t && !isPlaceholder(bestEl.t)){
    finish({found:true, ms:Date.now()-t0, text:bestEl.t, unstable:true});
  } else {
    finish({found:false, ms:Date.now()-t0});
  }
}, TIMEOUT_MS);

// The answer may already be rendered by the time the listener attaches.
onRender();
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
                # utf-8-sig: a hot-add seat file dropped from PowerShell/Notepad may carry
                # a BOM; json.loads chokes on it and would silently drop the chrome decl.
                raw = json.loads(self.secret.read_text(encoding="utf-8-sig"))
            except Exception:
                raw = {}
        self.host = host or raw.get("host") or ""
        # One Chrome, infinite sites (worklog #1112): the seat file may declare its own tab
        # substring inline ("chrome": {"tab": "chat.newsite.com"} or "chrome": "chat.newsite.com"
        # or "chrome": true). That lets a brand-new provider be served with ZERO registry
        # entry -- the site's own UI is the adapter, Chrome needs no adaptation.
        chrome_decl = raw.get("chrome")
        if isinstance(chrome_decl, dict) and chrome_decl.get("tab"):
            self.tab_substr = str(chrome_decl["tab"])
        elif isinstance(chrome_decl, str) and chrome_decl not in ("", "true", "True"):
            self.tab_substr = chrome_decl
        else:
            self.tab_substr = CHROME_CLIENTS.get(self.host, self.host)
        self.label = f"chrome/{self.host}"

    # ------------------------------------------------------------- plumbing ----
    def _focus_tab(self, driver):
        excludes = TAB_EXCLUDES.get(self.host, [])
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                u = driver.current_url or ""
                if self.tab_substr in u and not any(x in u for x in excludes):
                    try:
                        driver.execute_cdp_cmd("Page.bringToFront", {})
                    except Exception:
                        pass
                    return u
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
            sels = RESPONSE_SELECTORS.get(self.host, DEFAULT_RESPONSE_SELECTORS)
            snap = SNAP_JS.replace("__RESPONSE_SELECTORS__", sels)
            driver.execute_script("return " + snap.strip(), runid)

            # The human part of the play: focus the composer, then let Chrome deliver
            # the prompt as a real IME-level edit. The provider's own JS takes it from
            # there (encodes, sends, decodes, renders) -- we never touch its state.
            r1 = driver.execute_script("return " + FOCUS_JS.strip())
            if not r1.get("ok"):
                raise ChatError("NO_INPUT", r1.get("why", "no visible input"))
            injected = False
            try:
                driver.execute_cdp_cmd("Input.insertText", {"text": prompt})
                time.sleep(0.4)
                back = driver.execute_script("return " + READ_ACTIVE_JS.strip()) or {}
                injected = bool(back.get("ok")) and prompt[:40] in (back.get("text") or "")
            except Exception:
                injected = False
            if not injected:
                # Fallback for editors that refuse IME edits: legacy DOM injection.
                r1b = driver.execute_script("return " + INJECT_JS.strip(), prompt)
                if not r1b.get("ok"):
                    raise ChatError("TEXT_REJECTED", "composer did not accept the prompt")

            r2 = driver.execute_script("return " + SEND_JS.strip())
            time.sleep(2)
            if r2.get("remaining", 0) > 0:
                # Enter did not consume — some apps clear async (chatglm/cerebras), some
                # need a button. Click fallback; the listener below is the arbiter either way.
                driver.execute_script("return " + CLICK_JS.strip())
                time.sleep(2)

            listen = LISTEN_JS.replace("TIMEOUT_MS", str(ANSWER_TIMEOUT_S * 1000))
            listen = listen.replace("__RESPONSE_SELECTORS__", sels)
            r4 = driver.execute_async_script(listen, prompt, runid)

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
